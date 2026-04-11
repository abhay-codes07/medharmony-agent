"""MedHarmony Core Reconciliation Engine.

Orchestrates the full medication safety analysis pipeline:
1. Pull patient context from FHIR (or fall back to demo patient)
2. Reconcile medication lists
3. Analyze interactions (with MCP tool bridge)
4. Apply deprescribing guidelines (with MCP tool bridge)
5. Render clinician brief via Jinja2 template

Week 3 additions:
- ReasoningTracer: full observability of every LLM call and tool call
- AuditLog: HIPAA-style patient data access logging
- SafetyGuards: final-pass validation before returning results
- BriefRenderer: Jinja2-based deterministic brief formatting
- Demo-mode: load from sample_patient_ids.json for predictable demos
- Per-step try/except: one step failing never kills the whole pipeline
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from loguru import logger

from src.agent.config import SYNTHETIC_PATIENTS_DIR
from src.core.agent_loop import AgentLoop
from src.core.brief_templates import BriefRenderer, PatientBriefRenderer
from src.core.llm_client import LLMClient
from src.core.mcp_tool_bridge import MCPToolBridge
from src.core.safety_guards import SafetyGuards
from src.models.medication import (
    DeprescribingRecommendation,
    DrugInteraction,
    MedHarmonyResult,
    PatientContext,
    PrescribingCascade,
    ReconciliationEntry,
    Severity,
    SharpContext,
)
from src.utils.audit_log import AuditLog
from src.utils.fhir_client import FHIRClient
from src.utils.observability import ReasoningTracer

_SAMPLE_IDS_PATH = SYNTHETIC_PATIENTS_DIR / "sample_patient_ids.json"


class ReconciliationEngine:
    """Main orchestrator for MedHarmony analysis pipeline."""

    def __init__(self):
        self.llm = LLMClient()
        self._audit = AuditLog()
        self._guards = SafetyGuards()

    async def run_full_analysis(
        self,
        sharp_context: SharpContext,
        user_message: Optional[str] = None,
        demo_mode: bool = False,
    ) -> MedHarmonyResult:
        """Run the complete MedHarmony analysis pipeline.

        Args:
            sharp_context: SHARP context with patient_id and FHIR server URL.
            user_message: Optional free-text from the user (not used in core pipeline).
            demo_mode: If True, load patient from sample_patient_ids.json instead
                       of a live FHIR server (useful for predictable demos).

        Returns:
            MedHarmonyResult with full analysis, reasoning trace, and safety-validated output.
        """
        patient_id = sharp_context.patient_id or "unknown"
        logger.info(f"Starting full analysis for patient: {patient_id}")

        # Initialise observability and audit
        tracer = ReasoningTracer()
        self._audit.log_access(
            patient_id=patient_id,
            user_role=sharp_context.user_role or "system",
            action="full_medication_reconciliation",
            accessed_resources=[
                "Patient", "MedicationRequest", "MedicationStatement",
                "AllergyIntolerance", "Condition", "Observation",
            ],
            organization_id=sharp_context.organization_id,
        )

        # =====================================================================
        # Step 1: Pull patient context from FHIR (or fallback)
        # =====================================================================
        step_start = tracer.start_timer()
        patient_ctx: Optional[PatientContext] = None

        if demo_mode:
            patient_ctx = self._load_demo_patient(patient_id)
            tracer.record(
                "pipeline_step",
                tool_name="fhir_data_pull",
                result_summary=f"demo mode — loaded {patient_ctx.name}",
                duration_ms=tracer.elapsed(step_start),
            )
        else:
            fhir_client = FHIRClient(
                base_url=sharp_context.fhir_server_url or "https://hapi.fhir.org/baseR4",
                auth_token=sharp_context.fhir_access_token,
            )
            try:
                patient_ctx = await fhir_client.get_patient_context(patient_id)
                tracer.record(
                    "pipeline_step",
                    tool_name="fhir_data_pull",
                    result_summary=(
                        f"loaded {patient_ctx.name or patient_id} — "
                        f"{sum(len(ml.medications) for ml in patient_ctx.medication_lists)} meds"
                    ),
                    duration_ms=tracer.elapsed(step_start),
                )
                logger.info(f"FHIR data pulled: {patient_ctx.name}")
            except Exception as exc:
                tracer.record(
                    "error",
                    tool_name="fhir_data_pull",
                    error=self._guards.redact_phi(str(exc)),
                    duration_ms=tracer.elapsed(step_start),
                )
                self._audit.log_error(patient_id, "fhir_pull", str(exc))
                logger.warning(f"FHIR pull failed — falling back to demo patient: {exc}")
                patient_ctx = self._get_demo_patient_context(patient_id)

        # =====================================================================
        # Initialise MCP Tool Bridge
        # =====================================================================
        bridge: Optional[MCPToolBridge] = None
        step_start = tracer.start_timer()
        try:
            bridge = MCPToolBridge()
            await bridge.initialize()
            tool_count = sum(len(v) for v in bridge.list_all_tools().values())
            tracer.record(
                "pipeline_step",
                tool_name="mcp_bridge_init",
                result_summary=f"ready with {tool_count} tools",
                duration_ms=tracer.elapsed(step_start),
            )
            logger.info(f"MCPToolBridge ready: {tool_count} tools across 3 servers")
        except Exception as exc:
            tracer.record(
                "error",
                tool_name="mcp_bridge_init",
                error=str(exc),
                duration_ms=tracer.elapsed(step_start),
            )
            logger.warning(f"MCPToolBridge unavailable — running without MCP tools: {exc}")

        # Initialise partial result lists (each step writes to these)
        reconciliation: list[ReconciliationEntry] = []
        interactions: list[DrugInteraction] = []
        deprescribing: list[DeprescribingRecommendation] = []
        prescribing_cascades: list[PrescribingCascade] = []

        try:
            # =================================================================
            # Step 2: Reconcile medication lists
            # =================================================================
            logger.info("Step 2: Reconciling medication lists...")
            step_start = tracer.start_timer()
            try:
                reconciliation = await self._reconcile(patient_ctx)
                tracer.record(
                    "pipeline_step",
                    tool_name="medication_reconciliation",
                    result_summary=f"{len(reconciliation)} reconciliation entries",
                    duration_ms=tracer.elapsed(step_start),
                )
            except Exception as exc:
                tracer.record(
                    "error",
                    tool_name="medication_reconciliation",
                    error=str(exc),
                    duration_ms=tracer.elapsed(step_start),
                )
                logger.error(f"Reconciliation step failed: {exc}")
                # Continue with empty list — brief will note "Analysis incomplete"

            # =================================================================
            # Step 3: Analyze drug interactions
            # =================================================================
            logger.info("Step 3: Analyzing drug interactions...")
            step_start = tracer.start_timer()
            try:
                interactions = await self._analyze_interactions(patient_ctx, bridge, tracer)
                tracer.record(
                    "pipeline_step",
                    tool_name="interaction_analysis",
                    result_summary=f"{len(interactions)} interactions found",
                    duration_ms=tracer.elapsed(step_start),
                )
            except Exception as exc:
                tracer.record(
                    "error",
                    tool_name="interaction_analysis",
                    error=str(exc),
                    duration_ms=tracer.elapsed(step_start),
                )
                logger.error(f"Interaction analysis step failed: {exc}")

            # =================================================================
            # Step 4: Check deprescribing opportunities
            # =================================================================
            logger.info("Step 4: Checking deprescribing opportunities...")
            step_start = tracer.start_timer()
            try:
                deprescribing = await self._check_deprescribing(patient_ctx, bridge, tracer)
                tracer.record(
                    "pipeline_step",
                    tool_name="deprescribing_check",
                    result_summary=f"{len(deprescribing)} recommendations",
                    duration_ms=tracer.elapsed(step_start),
                )
            except Exception as exc:
                tracer.record(
                    "error",
                    tool_name="deprescribing_check",
                    error=str(exc),
                    duration_ms=tracer.elapsed(step_start),
                )
                logger.error(f"Deprescribing step failed: {exc}")

            # =================================================================
            # Step 4.5: Detect prescribing cascades (novel — multi-hop LLM)
            # =================================================================
            logger.info("Step 4.5: Detecting prescribing cascades...")
            step_start = tracer.start_timer()
            try:
                prescribing_cascades = await self._detect_cascades(patient_ctx)
                tracer.record(
                    "pipeline_step",
                    tool_name="cascade_detection",
                    result_summary=f"{len(prescribing_cascades)} cascade(s) detected",
                    duration_ms=tracer.elapsed(step_start),
                )
                if prescribing_cascades:
                    logger.info(
                        f"Cascade detector found {len(prescribing_cascades)} cascade(s): "
                        + ", ".join(c.root_medication for c in prescribing_cascades)
                    )
            except Exception as exc:
                tracer.record(
                    "error",
                    tool_name="cascade_detection",
                    error=str(exc),
                    duration_ms=tracer.elapsed(step_start),
                )
                logger.error(f"Cascade detection failed: {exc}")

        finally:
            if bridge:
                try:
                    await bridge.cleanup()
                except Exception as exc:
                    logger.warning(f"MCPToolBridge cleanup error: {exc}")

        # =====================================================================
        # Compile counts and tasks
        # =====================================================================
        critical = sum(
            1 for i in interactions if i.severity == Severity.CRITICAL
        ) + sum(
            1 for d in deprescribing if d.severity == Severity.CRITICAL
        )
        high = sum(
            1 for i in interactions if i.severity == Severity.HIGH
        ) + sum(
            1 for d in deprescribing if d.severity == Severity.HIGH
        )
        moderate = sum(
            1 for i in interactions if i.severity == Severity.MODERATE
        ) + sum(
            1 for d in deprescribing if d.severity == Severity.MODERATE
        )
        total_meds = sum(len(ml.medications) for ml in patient_ctx.medication_lists)
        tasks = self._build_tasks(interactions, deprescribing, reconciliation, prescribing_cascades)

        # Assemble result (without briefs — renderers need the complete result)
        result = MedHarmonyResult(
            patient_id=patient_ctx.patient_id,
            patient_name=patient_ctx.name,
            reconciliation=reconciliation,
            interactions=interactions,
            deprescribing=deprescribing,
            prescribing_cascades=prescribing_cascades,
            total_medications=total_meds,
            critical_issues=critical,
            high_issues=high,
            moderate_issues=moderate,
            clinician_brief="",
            patient_brief="",
            tasks=tasks,
            reasoning_trace=None,  # Will be set after brief generation
        )

        # =====================================================================
        # Step 5: Generate clinician brief via Jinja2 template
        # =====================================================================
        logger.info("Step 5: Generating clinician brief...")
        step_start = tracer.start_timer()
        try:
            renderer = BriefRenderer()
            result.clinician_brief = renderer.render(patient_ctx, result)
            tracer.record(
                "pipeline_step",
                tool_name="clinician_brief",
                result_summary=f"rendered {len(result.clinician_brief)} chars",
                duration_ms=tracer.elapsed(step_start),
            )
        except Exception as exc:
            tracer.record(
                "error",
                tool_name="clinician_brief",
                error=str(exc),
                duration_ms=tracer.elapsed(step_start),
            )
            logger.error(f"Brief generation failed: {exc}")
            result.clinician_brief = (
                f"## MedHarmony Safety Brief\n\n"
                f"**Note:** Brief rendering incomplete: {exc}\n\n"
                f"Analysis data is available in the structured JSON artifact."
            )

        # =====================================================================
        # Step 5.5: Generate patient-facing plain-language brief
        # =====================================================================
        logger.info("Step 5.5: Generating patient brief...")
        step_start = tracer.start_timer()
        try:
            patient_brief_data = await self.llm.generate_patient_brief_data(
                patient_context={
                    "patient_id": patient_ctx.patient_id,
                    "name": patient_ctx.name,
                    "age": patient_ctx.age,
                    "sex": patient_ctx.sex,
                },
                reconciliation=[r.model_dump() for r in reconciliation],
                interactions=[i.model_dump() for i in interactions],
                deprescribing=[d.model_dump() for d in deprescribing],
                cascades=[c.model_dump() for c in prescribing_cascades],
            )
            patient_renderer = PatientBriefRenderer()
            result.patient_brief = patient_renderer.render(patient_ctx, patient_brief_data)
            tracer.record(
                "pipeline_step",
                tool_name="patient_brief",
                result_summary=f"rendered {len(result.patient_brief)} chars",
                duration_ms=tracer.elapsed(step_start),
            )
        except Exception as exc:
            tracer.record(
                "error",
                tool_name="patient_brief",
                error=str(exc),
                duration_ms=tracer.elapsed(step_start),
            )
            logger.error(f"Patient brief generation failed: {exc}")
            result.patient_brief = PatientBriefRenderer._fallback(patient_ctx)

        # =====================================================================
        # Safety guards — final validation pass
        # =====================================================================
        result, guard_warnings = self._guards.run_all(result)
        result.safety_warnings = guard_warnings

        # Attach the final trace
        result.reasoning_trace = tracer.to_json()

        logger.info(
            f"Analysis complete: {critical} critical, {high} high, "
            f"{moderate} moderate issues | {total_meds} medications | "
            f"{len(tracer.entries)} trace steps"
        )
        return result

    # =========================================================================
    # Analysis sub-steps
    # =========================================================================

    async def _reconcile(
        self, patient_ctx: PatientContext
    ) -> list[ReconciliationEntry]:
        """Reconcile medication lists using LLM."""
        patient_dict = {
            "patient_id": patient_ctx.patient_id,
            "name": patient_ctx.name,
            "age": patient_ctx.age,
            "sex": patient_ctx.sex,
            "weight_kg": patient_ctx.weight_kg,
            "conditions": [c.model_dump() for c in patient_ctx.conditions],
            "allergies": [a.model_dump() for a in patient_ctx.allergies],
            "key_labs": [
                l.model_dump() for l in patient_ctx.lab_results if l.is_abnormal
            ],
        }
        med_lists = [ml.model_dump() for ml in patient_ctx.medication_lists]

        if not med_lists or all(len(ml["medications"]) == 0 for ml in med_lists):
            logger.warning("No medication lists to reconcile")
            return []

        raw = await self.llm.reconcile_medications(patient_dict, med_lists)
        return self._parse_reconciliation(raw)

    async def _analyze_interactions(
        self,
        patient_ctx: PatientContext,
        bridge: Optional[MCPToolBridge] = None,
        tracer: Optional[ReasoningTracer] = None,
    ) -> list[DrugInteraction]:
        """Analyze drug interactions using MCP tools when available."""
        all_meds = [
            med.model_dump()
            for ml in patient_ctx.medication_lists
            for med in ml.medications
        ]
        if not all_meds:
            return []

        patient_dict = {
            "patient_id": patient_ctx.patient_id,
            "age": patient_ctx.age,
            "sex": patient_ctx.sex,
            "weight_kg": patient_ctx.weight_kg,
            "conditions": [c.model_dump() for c in patient_ctx.conditions],
            "allergies": [a.model_dump() for a in patient_ctx.allergies],
            "lab_results": [l.model_dump() for l in patient_ctx.lab_results],
        }

        if bridge:
            context = (
                f"PATIENT CONTEXT:\n{json.dumps(patient_dict, indent=2)}\n\n"
                f"MEDICATIONS:\n{json.dumps(all_meds, indent=2)}"
            )
            prompt = """Use the available drug interaction tools to look up known
interactions between this patient's medications, then perform a comprehensive
clinical analysis considering their specific context (age, renal function,
allergies, conditions, lab values).

Identify all of:
1. Drug-drug interactions (pharmacokinetic and pharmacodynamic)
2. Drug-condition contraindications
3. Drug-allergy cross-reactivity
4. Drug-lab interactions
5. Duplicate therapy / therapeutic overlap

Respond with a JSON array only (no markdown fences):
[{"type":"drug-drug|drug-condition|drug-allergy|drug-lab|duplicate-therapy","severity":"critical|high|moderate|low","drug_a":"...","drug_b":"...","condition":"...","allergy":"...","lab":"...","description":"...","clinical_significance":"...","recommendation":"...","evidence_source":"..."}]"""
            loop = AgentLoop(self.llm, bridge, tracer=tracer)
            raw = await loop.run(
                prompt,
                context=context,
                tool_filter=["check_drug_interactions", "get_drug_info", "lookup_rxnorm"],
            )
        else:
            raw = await self.llm.analyze_interactions(patient_dict, all_meds, [])

        return self._parse_interactions(raw)

    async def _check_deprescribing(
        self,
        patient_ctx: PatientContext,
        bridge: Optional[MCPToolBridge] = None,
        tracer: Optional[ReasoningTracer] = None,
    ) -> list[DeprescribingRecommendation]:
        """Check for deprescribing opportunities using guideline MCP tools when available."""
        if patient_ctx.age and patient_ctx.age < 65:
            logger.info("Patient < 65, limited Beers Criteria applicability")

        all_meds = [
            med.model_dump()
            for ml in patient_ctx.medication_lists
            for med in ml.medications
        ]
        if not all_meds:
            return []

        patient_dict = {
            "patient_id": patient_ctx.patient_id,
            "age": patient_ctx.age,
            "sex": patient_ctx.sex,
            "weight_kg": patient_ctx.weight_kg,
            "conditions": [c.model_dump() for c in patient_ctx.conditions],
            "lab_results": [l.model_dump() for l in patient_ctx.lab_results],
        }

        if bridge:
            context = (
                f"PATIENT CONTEXT:\n{json.dumps(patient_dict, indent=2)}\n\n"
                f"MEDICATIONS:\n{json.dumps(all_meds, indent=2)}"
            )
            prompt = """Use the available clinical guideline tools to retrieve Beers
Criteria 2023 and STOPP/START v3 recommendations relevant to this patient's
medications, age, and renal function (eGFR). Then provide evidence-based
deprescribing recommendations for each applicable medication.

Respond with a JSON array only (no markdown fences):
[{"medication":"...","criteria":"...","reason":"...","recommendation":"...","severity":"critical|high|moderate|low","tapering_plan":"...","alternatives":["..."]}]"""
            loop = AgentLoop(self.llm, bridge, tracer=tracer)
            raw = await loop.run(
                prompt,
                context=context,
                tool_filter=[
                    "search_deprescribing_guidelines",
                    "get_beers_criteria",
                    "get_tapering_protocol",
                ],
            )
        else:
            raw = await self.llm.suggest_deprescribing(patient_dict, all_meds, [])

        return self._parse_deprescribing(raw)

    async def _detect_cascades(
        self, patient_ctx: PatientContext
    ) -> list[PrescribingCascade]:
        """Detect prescribing cascades using multi-hop LLM reasoning."""
        all_meds = [
            med.model_dump()
            for ml in patient_ctx.medication_lists
            for med in ml.medications
        ]
        if len(all_meds) < 2:
            return []

        # De-duplicate by name for cascade analysis (source doesn't matter here)
        seen = set()
        unique_meds = []
        for m in all_meds:
            if m["name"].lower() not in seen:
                seen.add(m["name"].lower())
                unique_meds.append(m)

        patient_dict = {
            "patient_id": patient_ctx.patient_id,
            "age": patient_ctx.age,
            "sex": patient_ctx.sex,
            "conditions": [c.model_dump() for c in patient_ctx.conditions],
            "lab_results": [l.model_dump() for l in patient_ctx.lab_results],
        }

        raw = await self.llm.detect_prescribing_cascades(patient_dict, unique_meds)
        return self._parse_cascades(raw)

    def _build_tasks(
        self,
        interactions: list[DrugInteraction],
        deprescribing: list[DeprescribingRecommendation],
        reconciliation: list[ReconciliationEntry],
        cascades: Optional[list[PrescribingCascade]] = None,
    ) -> list[str]:
        """Build follow-up task list for clinician."""
        tasks = []

        for ix in interactions:
            if ix.severity in (Severity.CRITICAL, Severity.HIGH):
                tasks.append(
                    f"[{ix.severity.value.upper()}] Review {ix.type.value}: "
                    f"{ix.drug_a}" + (f" + {ix.drug_b}" if ix.drug_b else "") +
                    f" — {ix.recommendation}"
                )

        for dp in deprescribing:
            if dp.severity in (Severity.CRITICAL, Severity.HIGH):
                tasks.append(
                    f"[DEPRESCRIBE] Review {dp.medication}: {dp.recommendation} "
                    f"(per {dp.criteria})"
                )

        for rec in reconciliation:
            if rec.action.value == "review":
                tasks.append(
                    f"[RECONCILE] Resolve discrepancy for {rec.medication}: {rec.reason}"
                )

        # Cascade tasks — highlight high/critical chains for unwind consideration
        for cascade in (cascades or []):
            if cascade.severity in (Severity.CRITICAL, Severity.HIGH):
                chain_str = " → ".join(cascade.chain)
                tasks.append(
                    f"[CASCADE] Review prescribing cascade: {chain_str} — "
                    f"{cascade.recommendation}"
                )

        return tasks

    # =========================================================================
    # Demo / Synthetic Patient Loaders
    # =========================================================================

    def _load_demo_patient(self, patient_id: str) -> PatientContext:
        """Load a patient from sample_patient_ids.json for predictable demos.

        Falls back to the hardcoded demo patient if the file is missing or
        if the patient_id is 'demo-001'.
        """
        if patient_id == "demo-001" or not _SAMPLE_IDS_PATH.exists():
            return self._get_demo_patient_context(patient_id)

        try:
            records = json.loads(_SAMPLE_IDS_PATH.read_text(encoding="utf-8"))
            record = next((r for r in records if r["patient_id"] == patient_id), None)
            if record and record.get("fhir_server") != "local-demo":
                # Real patient — fetch from FHIR synchronously is not ideal here,
                # but demo mode is expected to fall through to the async path.
                # For simplicity in demo mode, always fall back to demo-001.
                logger.info(
                    f"Demo mode: patient {patient_id} is a live HAPI patient; "
                    "falling back to built-in demo patient for offline demo"
                )
        except Exception as exc:
            logger.warning(f"Could not load sample_patient_ids.json: {exc}")

        return self._get_demo_patient_context(patient_id)

    def _get_demo_patient_context(self, patient_id: str) -> PatientContext:
        """Return a rich synthetic patient for offline demo and testing.

        Margaret Thompson is an intentionally complex patient with multiple
        medication safety issues — designed to demonstrate every MedHarmony
        analysis capability.

        This is the FALLBACK used when:
        - FHIR pull fails
        - demo_mode=True and patient_id == 'demo-001'
        """
        from src.models.medication import (
            Allergy, Condition, LabResult, Medication, MedicationList,
        )

        return PatientContext(
            patient_id=patient_id or "demo-001",
            name="Margaret Thompson",
            age=78,
            sex="female",
            weight_kg=62.0,
            allergies=[
                Allergy(substance="Penicillin", reaction="Anaphylaxis", severity="high"),
                Allergy(substance="Sulfonamides", reaction="Rash", severity="low"),
            ],
            conditions=[
                Condition(name="Type 2 Diabetes Mellitus", icd10_code="E11.9"),
                Condition(name="Essential Hypertension", icd10_code="I10"),
                Condition(name="Atrial Fibrillation", icd10_code="I48.91"),
                Condition(name="Chronic Kidney Disease Stage 3b", icd10_code="N18.32"),
                Condition(name="Osteoarthritis", icd10_code="M19.90"),
                Condition(name="GERD", icd10_code="K21.0"),
                Condition(name="Insomnia", icd10_code="G47.00"),
                Condition(name="Generalized Anxiety Disorder", icd10_code="F41.1"),
            ],
            lab_results=[
                LabResult(name="Creatinine", loinc_code="2160-0", value=1.8, unit="mg/dL",
                          reference_range="0.6-1.2", is_abnormal=True),
                LabResult(name="eGFR", loinc_code="33914-3", value=32.0,
                          unit="mL/min/1.73m2", reference_range=">60", is_abnormal=True),
                LabResult(name="Potassium", loinc_code="2823-3", value=5.3, unit="mEq/L",
                          reference_range="3.5-5.0", is_abnormal=True),
                LabResult(name="HbA1c", loinc_code="4548-4", value=7.8, unit="%",
                          reference_range="<7.0", is_abnormal=True),
                LabResult(name="INR", loinc_code="49765-1", value=2.8, unit="",
                          reference_range="2.0-3.0", is_abnormal=False),
                LabResult(name="ALT", loinc_code="1742-6", value=22.0, unit="U/L",
                          reference_range="7-56", is_abnormal=False),
                LabResult(name="Hemoglobin", loinc_code="718-7", value=10.8, unit="g/dL",
                          reference_range="12-16", is_abnormal=True),
                LabResult(name="Platelets", loinc_code="777-3", value=145.0,
                          unit="10*3/uL", reference_range="150-400", is_abnormal=True),
            ],
            medication_lists=[
                MedicationList(
                    source="admission_home_meds",
                    medications=[
                        Medication(name="Metformin", dose="1000 mg", frequency="twice daily",
                                   route="oral", rxnorm_code="861004"),
                        Medication(name="Warfarin", dose="5 mg", frequency="daily",
                                   route="oral", rxnorm_code="855332"),
                        Medication(name="Lisinopril", dose="20 mg", frequency="daily",
                                   route="oral", rxnorm_code="314076"),
                        Medication(name="Amlodipine", dose="10 mg", frequency="daily",
                                   route="oral", rxnorm_code="197361"),
                        Medication(name="Metoprolol Tartrate", dose="50 mg",
                                   frequency="twice daily", route="oral", rxnorm_code="866514"),
                        Medication(name="Omeprazole", dose="20 mg", frequency="daily",
                                   route="oral", rxnorm_code="198053"),
                        Medication(name="Ibuprofen", dose="400 mg",
                                   frequency="three times daily", route="oral",
                                   rxnorm_code="197806"),
                        Medication(name="Diazepam", dose="5 mg", frequency="at bedtime",
                                   route="oral", rxnorm_code="197591"),
                        Medication(name="Diphenhydramine", dose="25 mg",
                                   frequency="at bedtime", route="oral", rxnorm_code="1049630"),
                        Medication(name="Furosemide", dose="40 mg", frequency="daily",
                                   route="oral", rxnorm_code="197417"),
                        Medication(name="Potassium Chloride", dose="20 mEq",
                                   frequency="daily", route="oral", rxnorm_code="198082"),
                        Medication(name="Atorvastatin", dose="40 mg", frequency="at bedtime",
                                   route="oral", rxnorm_code="259255"),
                    ],
                ),
                MedicationList(
                    source="discharge_medications",
                    medications=[
                        Medication(name="Metformin", dose="500 mg", frequency="twice daily",
                                   route="oral", rxnorm_code="861004"),
                        Medication(name="Warfarin", dose="5 mg", frequency="daily",
                                   route="oral", rxnorm_code="855332"),
                        Medication(name="Lisinopril", dose="10 mg", frequency="daily",
                                   route="oral", rxnorm_code="314076"),
                        Medication(name="Amlodipine", dose="10 mg", frequency="daily",
                                   route="oral", rxnorm_code="197361"),
                        Medication(name="Metoprolol Succinate ER", dose="100 mg",
                                   frequency="daily", route="oral", rxnorm_code="866924"),
                        Medication(name="Pantoprazole", dose="40 mg", frequency="daily",
                                   route="oral", rxnorm_code="261257"),
                        Medication(name="Acetaminophen", dose="650 mg",
                                   frequency="as needed", route="oral", rxnorm_code="313782"),
                        Medication(name="Furosemide", dose="40 mg", frequency="daily",
                                   route="oral", rxnorm_code="197417"),
                        Medication(name="Potassium Chloride", dose="40 mEq",
                                   frequency="daily", route="oral", rxnorm_code="198082"),
                        Medication(name="Atorvastatin", dose="40 mg", frequency="at bedtime",
                                   route="oral", rxnorm_code="259255"),
                        Medication(name="Apixaban", dose="5 mg", frequency="twice daily",
                                   route="oral", rxnorm_code="1364430"),
                    ],
                ),
            ],
        )

    # =========================================================================
    # JSON Parsers (extract structured data from LLM responses)
    # =========================================================================

    def _parse_json_from_llm(self, raw: str) -> list[dict]:
        """Extract JSON array from LLM response (handles markdown fences)."""
        text = raw.strip()

        if "```json" in text:
            text = text.split("```json")[1]
        if "```" in text:
            text = text.split("```")[0]

        text = text.strip()

        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        logger.warning("Failed to parse JSON from LLM response")
        return []

    def _parse_cascades(self, raw: str) -> list[PrescribingCascade]:
        """Parse prescribing cascade entries from LLM response."""
        items = self._parse_json_from_llm(raw)
        entries = []
        for item in items:
            try:
                entries.append(PrescribingCascade(
                    chain=item.get("chain", []),
                    chain_description=item.get("chain_description", ""),
                    root_medication=item.get("root_medication", "Unknown"),
                    root_side_effect=item.get("root_side_effect", ""),
                    cascade_depth=item.get("cascade_depth", len(item.get("chain", [])) - 1),
                    severity=item.get("severity", "moderate"),
                    recommendation=item.get("recommendation", ""),
                    medications_to_review=item.get("medications_to_review", []),
                    evidence_source=item.get("evidence_source"),
                ))
            except Exception as exc:
                logger.warning(f"Failed to parse cascade: {exc}")
        return entries

    def _parse_reconciliation(self, raw: str) -> list[ReconciliationEntry]:
        items = self._parse_json_from_llm(raw)
        entries = []
        for item in items:
            try:
                entries.append(ReconciliationEntry(
                    medication=item.get("medication", "Unknown"),
                    action=item.get("action", "review"),
                    reason=item.get("reason", ""),
                    from_source=item.get("from_source"),
                    current_dose=item.get("current_dose"),
                    recommended_dose=item.get("recommended_dose"),
                    notes=item.get("notes"),
                ))
            except Exception as exc:
                logger.warning(f"Failed to parse reconciliation entry: {exc}")
        return entries

    def _parse_interactions(self, raw: str) -> list[DrugInteraction]:
        items = self._parse_json_from_llm(raw)
        entries = []
        for item in items:
            try:
                entries.append(DrugInteraction(
                    type=item.get("type", "drug-drug"),
                    severity=item.get("severity", "moderate"),
                    drug_a=item.get("drug_a", "Unknown"),
                    drug_b=item.get("drug_b"),
                    condition=item.get("condition"),
                    allergy=item.get("allergy"),
                    lab=item.get("lab"),
                    description=item.get("description", ""),
                    clinical_significance=item.get("clinical_significance", ""),
                    recommendation=item.get("recommendation", ""),
                    evidence_source=item.get("evidence_source"),
                ))
            except Exception as exc:
                logger.warning(f"Failed to parse interaction: {exc}")
        return entries

    def _parse_deprescribing(self, raw: str) -> list[DeprescribingRecommendation]:
        items = self._parse_json_from_llm(raw)
        entries = []
        for item in items:
            try:
                entries.append(DeprescribingRecommendation(
                    medication=item.get("medication", "Unknown"),
                    criteria=item.get("criteria", ""),
                    reason=item.get("reason", ""),
                    recommendation=item.get("recommendation", ""),
                    severity=item.get("severity", "moderate"),
                    tapering_plan=item.get("tapering_plan"),
                    alternatives=item.get("alternatives", []),
                ))
            except Exception as exc:
                logger.warning(f"Failed to parse deprescribing rec: {exc}")
        return entries
