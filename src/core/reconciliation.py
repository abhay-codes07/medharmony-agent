"""MedHarmony Core Reconciliation Engine.

Orchestrates the full medication safety analysis pipeline:
1. Pull patient context from FHIR
2. Reconcile medication lists
3. Analyze interactions
4. Apply deprescribing guidelines
5. Generate clinician brief
"""

from __future__ import annotations

import json
from typing import Optional

from loguru import logger

from src.core.agent_loop import AgentLoop
from src.core.llm_client import LLMClient
from src.core.mcp_tool_bridge import MCPToolBridge
from src.models.medication import (
    DeprescribingRecommendation,
    DrugInteraction,
    MedHarmonyResult,
    PatientContext,
    ReconciliationEntry,
    Severity,
    SharpContext,
)
from src.utils.fhir_client import FHIRClient


class ReconciliationEngine:
    """Main orchestrator for MedHarmony analysis pipeline."""

    def __init__(self):
        self.llm = LLMClient()

    async def run_full_analysis(
        self,
        sharp_context: SharpContext,
        user_message: Optional[str] = None,
    ) -> MedHarmonyResult:
        """Run the complete MedHarmony analysis pipeline."""
        logger.info(f"Starting full analysis for patient: {sharp_context.patient_id}")

        # =====================================================================
        # Step 1: Pull patient context from FHIR
        # =====================================================================
        fhir_client = FHIRClient(
            base_url=sharp_context.fhir_server_url or "https://hapi.fhir.org/baseR4",
            auth_token=sharp_context.fhir_access_token,
        )

        try:
            patient_ctx = await fhir_client.get_patient_context(
                sharp_context.patient_id
            )
        except Exception as e:
            logger.error(f"Failed to pull FHIR data: {e}")
            # Fall back to synthetic data if FHIR pull fails
            patient_ctx = self._get_demo_patient_context(sharp_context.patient_id)

        # =====================================================================
        # Initialize MCP Tool Bridge for agentic tool use
        # =====================================================================
        bridge: Optional[MCPToolBridge] = None
        try:
            bridge = MCPToolBridge()
            await bridge.initialize()
            tool_count = sum(len(v) for v in bridge.list_all_tools().values())
            logger.info(f"MCPToolBridge ready: {tool_count} tools across 3 servers")
        except Exception as e:
            logger.warning(
                f"MCPToolBridge unavailable — running without MCP tools: {e}"
            )

        try:
            # =====================================================================
            # Step 2: Reconcile medication lists
            # =====================================================================
            logger.info("Step 2: Reconciling medication lists...")
            reconciliation = await self._reconcile(patient_ctx)

            # =====================================================================
            # Step 3: Analyze drug interactions (with MCP drug interaction tools)
            # =====================================================================
            logger.info("Step 3: Analyzing drug interactions...")
            interactions = await self._analyze_interactions(patient_ctx, bridge)

            # =====================================================================
            # Step 4: Apply deprescribing guidelines (with MCP guideline tools)
            # =====================================================================
            logger.info("Step 4: Checking deprescribing opportunities...")
            deprescribing = await self._check_deprescribing(patient_ctx, bridge)

            # =====================================================================
            # Step 5: Generate clinician brief
            # =====================================================================
            logger.info("Step 5: Generating clinician brief...")
            brief = await self._generate_brief(
                patient_ctx, reconciliation, interactions, deprescribing
            )

        finally:
            if bridge:
                await bridge.cleanup()

        # =====================================================================
        # Compile final result
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

        total_meds = sum(
            len(ml.medications) for ml in patient_ctx.medication_lists
        )

        # Build follow-up tasks
        tasks = self._build_tasks(interactions, deprescribing, reconciliation)

        result = MedHarmonyResult(
            patient_id=patient_ctx.patient_id,
            patient_name=patient_ctx.name,
            reconciliation=reconciliation,
            interactions=interactions,
            deprescribing=deprescribing,
            total_medications=total_meds,
            critical_issues=critical,
            high_issues=high,
            moderate_issues=moderate,
            clinician_brief=brief,
            tasks=tasks,
        )

        logger.info(
            f"Analysis complete: {critical} critical, {high} high, "
            f"{moderate} moderate issues found across {total_meds} medications"
        )
        return result

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
    ) -> list[DrugInteraction]:
        """Analyze drug interactions, using MCP drug interaction tools when available."""
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
            loop = AgentLoop(self.llm, bridge)
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
            loop = AgentLoop(self.llm, bridge)
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

    async def _generate_brief(
        self,
        patient_ctx: PatientContext,
        reconciliation: list[ReconciliationEntry],
        interactions: list[DrugInteraction],
        deprescribing: list[DeprescribingRecommendation],
    ) -> str:
        """Generate the clinician safety brief."""
        patient_dict = {
            "patient_id": patient_ctx.patient_id,
            "name": patient_ctx.name,
            "age": patient_ctx.age,
            "sex": patient_ctx.sex,
        }

        raw = await self.llm.generate_clinician_brief(
            patient_dict,
            [r.model_dump() for r in reconciliation],
            [i.model_dump() for i in interactions],
            [d.model_dump() for d in deprescribing],
        )
        return raw

    def _build_tasks(
        self,
        interactions: list[DrugInteraction],
        deprescribing: list[DeprescribingRecommendation],
        reconciliation: list[ReconciliationEntry],
    ) -> list[str]:
        """Build follow-up task list for clinician."""
        tasks = []

        # Critical interactions need immediate action
        for ix in interactions:
            if ix.severity in (Severity.CRITICAL, Severity.HIGH):
                tasks.append(
                    f"[{ix.severity.value.upper()}] Review {ix.type.value}: "
                    f"{ix.drug_a}" + (f" + {ix.drug_b}" if ix.drug_b else "") +
                    f" — {ix.recommendation}"
                )

        # Deprescribing opportunities
        for dp in deprescribing:
            if dp.severity in (Severity.CRITICAL, Severity.HIGH):
                tasks.append(
                    f"[DEPRESCRIBE] Review {dp.medication}: {dp.recommendation} "
                    f"(per {dp.criteria})"
                )

        # Reconciliation items needing review
        for rec in reconciliation:
            if rec.action.value == "review":
                tasks.append(
                    f"[RECONCILE] Resolve discrepancy for {rec.medication}: {rec.reason}"
                )

        return tasks

    # =========================================================================
    # JSON Parsers (extract structured data from LLM responses)
    # =========================================================================

    def _parse_json_from_llm(self, raw: str) -> list[dict]:
        """Extract JSON array from LLM response (handles markdown fences)."""
        text = raw.strip()

        # Remove markdown code fences
        if "```json" in text:
            text = text.split("```json")[1]
        if "```" in text:
            text = text.split("```")[0]

        text = text.strip()

        # Try to find JSON array
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        logger.warning("Failed to parse JSON from LLM response")
        return []

    def _parse_reconciliation(self, raw: str) -> list[ReconciliationEntry]:
        """Parse reconciliation entries from LLM response."""
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
            except Exception as e:
                logger.warning(f"Failed to parse reconciliation entry: {e}")
        return entries

    def _parse_interactions(self, raw: str) -> list[DrugInteraction]:
        """Parse interaction entries from LLM response."""
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
            except Exception as e:
                logger.warning(f"Failed to parse interaction: {e}")
        return entries

    def _parse_deprescribing(self, raw: str) -> list[DeprescribingRecommendation]:
        """Parse deprescribing entries from LLM response."""
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
            except Exception as e:
                logger.warning(f"Failed to parse deprescribing rec: {e}")
        return entries

    # =========================================================================
    # Demo / Synthetic Patient (for hackathon demo)
    # =========================================================================

    def _get_demo_patient_context(self, patient_id: str) -> PatientContext:
        """Return a synthetic complex patient for offline demo and testing."""
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
                LabResult(name="Creatinine", loinc_code="2160-0", value=1.8, unit="mg/dL", reference_range="0.6-1.2", is_abnormal=True),
                LabResult(name="eGFR", loinc_code="33914-3", value=32.0, unit="mL/min/1.73m2", reference_range=">60", is_abnormal=True),
                LabResult(name="Potassium", loinc_code="2823-3", value=5.3, unit="mEq/L", reference_range="3.5-5.0", is_abnormal=True),
                LabResult(name="HbA1c", loinc_code="4548-4", value=7.8, unit="%", reference_range="<7.0", is_abnormal=True),
                LabResult(name="INR", loinc_code="49765-1", value=2.8, unit="", reference_range="2.0-3.0", is_abnormal=False),
                LabResult(name="ALT", loinc_code="1742-6", value=22.0, unit="U/L", reference_range="7-56", is_abnormal=False),
                LabResult(name="Hemoglobin", loinc_code="718-7", value=10.8, unit="g/dL", reference_range="12-16", is_abnormal=True),
                LabResult(name="Platelets", loinc_code="777-3", value=145.0, unit="10*3/uL", reference_range="150-400", is_abnormal=True),
            ],
            medication_lists=[
                MedicationList(
                    source="admission_home_meds",
                    medications=[
                        Medication(name="Metformin", dose="1000 mg", frequency="twice daily", route="oral", rxnorm_code="861004"),
                        Medication(name="Warfarin", dose="5 mg", frequency="daily", route="oral", rxnorm_code="855332"),
                        Medication(name="Lisinopril", dose="20 mg", frequency="daily", route="oral", rxnorm_code="314076"),
                        Medication(name="Amlodipine", dose="10 mg", frequency="daily", route="oral", rxnorm_code="197361"),
                        Medication(name="Metoprolol Tartrate", dose="50 mg", frequency="twice daily", route="oral", rxnorm_code="866514"),
                        Medication(name="Omeprazole", dose="20 mg", frequency="daily", route="oral", rxnorm_code="198053"),
                        Medication(name="Ibuprofen", dose="400 mg", frequency="three times daily", route="oral", rxnorm_code="197806"),
                        Medication(name="Diazepam", dose="5 mg", frequency="at bedtime", route="oral", rxnorm_code="197591"),
                        Medication(name="Diphenhydramine", dose="25 mg", frequency="at bedtime", route="oral", rxnorm_code="1049630"),
                        Medication(name="Furosemide", dose="40 mg", frequency="daily", route="oral", rxnorm_code="197417"),
                        Medication(name="Potassium Chloride", dose="20 mEq", frequency="daily", route="oral", rxnorm_code="198082"),
                        Medication(name="Atorvastatin", dose="40 mg", frequency="at bedtime", route="oral", rxnorm_code="259255"),
                    ],
                ),
                MedicationList(
                    source="discharge_medications",
                    medications=[
                        Medication(name="Metformin", dose="500 mg", frequency="twice daily", route="oral", rxnorm_code="861004"),
                        Medication(name="Warfarin", dose="5 mg", frequency="daily", route="oral", rxnorm_code="855332"),
                        Medication(name="Lisinopril", dose="10 mg", frequency="daily", route="oral", rxnorm_code="314076"),
                        Medication(name="Amlodipine", dose="10 mg", frequency="daily", route="oral", rxnorm_code="197361"),
                        Medication(name="Metoprolol Succinate ER", dose="100 mg", frequency="daily", route="oral", rxnorm_code="866924"),
                        Medication(name="Pantoprazole", dose="40 mg", frequency="daily", route="oral", rxnorm_code="261257"),
                        Medication(name="Acetaminophen", dose="650 mg", frequency="as needed", route="oral", rxnorm_code="313782"),
                        Medication(name="Furosemide", dose="40 mg", frequency="daily", route="oral", rxnorm_code="197417"),
                        Medication(name="Potassium Chloride", dose="40 mEq", frequency="daily", route="oral", rxnorm_code="198082"),
                        Medication(name="Atorvastatin", dose="40 mg", frequency="at bedtime", route="oral", rxnorm_code="259255"),
                        Medication(name="Apixaban", dose="5 mg", frequency="twice daily", route="oral", rxnorm_code="1364430"),
                    ],
                ),
            ],
        )
