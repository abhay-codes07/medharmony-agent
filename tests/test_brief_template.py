"""Unit tests for the Jinja2 clinician brief template system.

Tests rendering with full and partial data, verifying section visibility.
No network calls — uses in-memory mock data only.
"""

from __future__ import annotations

import pytest

from src.core.brief_templates import BriefRenderer, PatientBriefRenderer, _build_reconciliation_rows
from src.models.medication import (
    Allergy,
    Condition,
    DeprescribingRecommendation,
    DrugInteraction,
    InteractionType,
    LabResult,
    Medication,
    MedicationList,
    MedHarmonyResult,
    PatientContext,
    PrescribingCascade,
    ReconciliationAction,
    ReconciliationEntry,
    Severity,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_patient(
    name="Test Patient",
    age=75,
    sex="female",
    weight_kg=65.0,
    egfr=35.0,
    allergies=None,
    conditions=None,
    medications=None,
) -> PatientContext:
    return PatientContext(
        patient_id="test-001",
        name=name,
        age=age,
        sex=sex,
        weight_kg=weight_kg,
        allergies=(
            [Allergy(substance="Penicillin", reaction="Rash", severity="low")]
            if allergies is None else allergies
        ),
        conditions=conditions or [Condition(name="CKD Stage 3", icd10_code="N18.3")],
        lab_results=[
            LabResult(
                name="eGFR",
                loinc_code="33914-3",
                value=egfr,
                unit="mL/min/1.73m2",
                reference_range=">60",
                is_abnormal=True,
            )
        ],
        medication_lists=medications or [
            MedicationList(
                source="admission_home_meds",
                medications=[
                    Medication(name="Warfarin", dose="5 mg", frequency="daily", route="oral"),
                    Medication(name="Ibuprofen", dose="400 mg", frequency="TID", route="oral"),
                ],
            ),
            MedicationList(
                source="discharge_medications",
                medications=[
                    Medication(name="Warfarin", dose="5 mg", frequency="daily", route="oral"),
                    Medication(name="Acetaminophen", dose="650 mg", frequency="PRN", route="oral"),
                ],
            ),
        ],
    )


def _make_interaction(severity=Severity.CRITICAL) -> DrugInteraction:
    return DrugInteraction(
        type=InteractionType.DRUG_DRUG,
        severity=severity,
        drug_a="Warfarin",
        drug_b="Ibuprofen",
        description="Increased bleeding risk",
        clinical_significance="Critical in anticoagulated elderly patient",
        recommendation="Discontinue ibuprofen for clinician review",
        evidence_source="Beers Criteria 2023",
    )


def _make_deprescribing() -> DeprescribingRecommendation:
    return DeprescribingRecommendation(
        medication="Diazepam",
        criteria="Beers Criteria 2023",
        reason="Falls risk in elderly",
        recommendation="Taper and discontinue for clinician review",
        severity=Severity.HIGH,
        tapering_plan="Week 1-2: halve dose; Week 3-4: every other day; Week 5: stop",
        alternatives=["Melatonin", "CBT-I"],
    )


def _make_reconciliation() -> ReconciliationEntry:
    return ReconciliationEntry(
        medication="Ibuprofen",
        action=ReconciliationAction.DISCONTINUE,
        reason="NSAID contraindicated in CKD + anticoagulation",
        from_source="admission_home_meds",
        current_dose="400 mg TID",
        recommended_dose=None,
    )


def _make_cascade(severity=Severity.HIGH) -> PrescribingCascade:
    return PrescribingCascade(
        chain=["Amlodipine", "Furosemide", "Potassium Chloride"],
        chain_description=(
            "Amlodipine causes ankle edema, leading to furosemide prescription. "
            "Furosemide causes potassium loss, leading to KCl supplement. "
            "But patient is on ACE inhibitor retaining K+ — hyperkalemia risk."
        ),
        root_medication="Amlodipine",
        root_side_effect="Peripheral edema (ankle swelling)",
        cascade_depth=2,
        severity=severity,
        recommendation="Consider switching amlodipine to a non-CCB antihypertensive to unwind the cascade",
        medications_to_review=["Furosemide", "Potassium Chloride"],
        evidence_source="Clinical pharmacology guidelines; STOPP v3",
    )


def _make_result(
    interactions=None,
    deprescribing=None,
    reconciliation=None,
    cascades=None,
    critical_issues=0,
    high_issues=0,
    tasks=None,
) -> MedHarmonyResult:
    return MedHarmonyResult(
        patient_id="test-001",
        patient_name="Test Patient",
        reconciliation=reconciliation or [],
        interactions=interactions or [],
        deprescribing=deprescribing or [],
        prescribing_cascades=cascades or [],
        total_medications=4,
        critical_issues=critical_issues,
        high_issues=high_issues,
        moderate_issues=0,
        clinician_brief="Fallback brief text",
        patient_brief="",
        tasks=tasks or ["Review warfarin dose", "Discontinue ibuprofen"],
    )


# ---------------------------------------------------------------------------
# BriefRenderer tests
# ---------------------------------------------------------------------------


class TestBriefRenderer:
    def setup_method(self):
        self.renderer = BriefRenderer()

    def test_renders_without_crashing_on_full_data(self):
        """Full data set should render to a non-empty markdown string."""
        patient = _make_patient()
        result = _make_result(
            interactions=[_make_interaction(Severity.CRITICAL)],
            deprescribing=[_make_deprescribing()],
            reconciliation=[_make_reconciliation()],
            critical_issues=1,
            high_issues=0,
        )
        brief = self.renderer.render(patient, result)
        assert isinstance(brief, str)
        assert len(brief) > 200

    def test_header_contains_patient_info(self):
        """Brief header should show patient name, age, sex, weight, eGFR."""
        patient = _make_patient(name="Eleanor Vance", age=79, sex="female", egfr=32.0)
        result = _make_result()
        brief = self.renderer.render(patient, result)
        assert "Eleanor Vance" in brief
        assert "79" in brief
        assert "32.0" in brief or "32" in brief  # eGFR

    def test_critical_alerts_section_shown_when_present(self):
        """🚨 Critical Alerts section must appear when critical_issues > 0."""
        patient = _make_patient()
        result = _make_result(
            interactions=[_make_interaction(Severity.CRITICAL)],
            critical_issues=1,
        )
        brief = self.renderer.render(patient, result)
        assert "Critical Alerts" in brief
        assert "Immediate clinician review" in brief

    def test_critical_alerts_hidden_when_none(self):
        """🚨 Critical Alerts section must NOT appear when there are no critical issues."""
        patient = _make_patient()
        result = _make_result(
            interactions=[_make_interaction(Severity.MODERATE)],
            critical_issues=0,
        )
        brief = self.renderer.render(patient, result)
        assert "Critical Alerts" not in brief

    def test_reconciliation_table_rendered(self):
        """Reconciliation table should appear with medication names."""
        patient = _make_patient()
        result = _make_result(reconciliation=[_make_reconciliation()])
        brief = self.renderer.render(patient, result)
        assert "Medication Reconciliation" in brief
        assert "Ibuprofen" in brief

    def test_interaction_findings_section_present(self):
        """Drug interaction findings section should appear."""
        patient = _make_patient()
        result = _make_result(interactions=[_make_interaction(Severity.HIGH)])
        brief = self.renderer.render(patient, result)
        assert "Drug Interaction" in brief
        assert "Warfarin" in brief

    def test_no_interactions_message_when_empty(self):
        """A no-interaction message should appear when interactions list is empty."""
        patient = _make_patient()
        result = _make_result(interactions=[])
        brief = self.renderer.render(patient, result)
        assert "No significant drug interactions" in brief

    def test_deprescribing_section_shown_when_present(self):
        """Deprescribing section should appear when recommendations exist."""
        patient = _make_patient()
        result = _make_result(deprescribing=[_make_deprescribing()])
        brief = self.renderer.render(patient, result)
        assert "Deprescribing" in brief
        assert "Diazepam" in brief

    def test_deprescribing_section_shows_tapering_plan(self):
        """Tapering plan should appear if the deprescribing rec has one."""
        patient = _make_patient()
        dep = _make_deprescribing()
        dep.tapering_plan = "Reduce by 25% weekly"
        result = _make_result(deprescribing=[dep])
        brief = self.renderer.render(patient, result)
        assert "Tapering" in brief
        assert "25%" in brief

    def test_deprescribing_hidden_when_empty(self):
        """'No deprescribing opportunities' message should appear when list is empty."""
        patient = _make_patient()
        result = _make_result(deprescribing=[])
        brief = self.renderer.render(patient, result)
        assert "No medications identified" in brief

    def test_recommended_actions_from_tasks(self):
        """Recommended actions should reflect the tasks list."""
        patient = _make_patient()
        result = _make_result(tasks=["Action A", "Action B: check INR"])
        brief = self.renderer.render(patient, result)
        assert "Action A" in brief
        assert "Action B" in brief

    def test_summary_stats_table_present(self):
        """Summary stats table should appear with correct counts."""
        patient = _make_patient()
        result = _make_result(critical_issues=2, high_issues=1)
        brief = self.renderer.render(patient, result)
        assert "Summary" in brief
        assert "Total Medications" in brief

    def test_signature_line_present(self):
        """MedHarmony signature line must appear at the bottom."""
        patient = _make_patient()
        result = _make_result()
        brief = self.renderer.render(patient, result, clinician_name="Dr. Smith")
        assert "MedHarmony" in brief
        assert "Dr. Smith" in brief
        assert "clinical decision support" in brief.lower()

    def test_allergies_shown_in_header(self):
        """Allergies should appear in the patient header line."""
        patient = _make_patient(
            allergies=[
                Allergy(substance="Penicillin", reaction="Anaphylaxis", severity="high"),
                Allergy(substance="Sulfonamides", reaction="Rash", severity="low"),
            ]
        )
        result = _make_result()
        brief = self.renderer.render(patient, result)
        assert "Penicillin" in brief
        assert "Sulfonamides" in brief

    def test_nkda_shown_when_no_allergies(self):
        """'NKDA' should appear when no allergies are listed."""
        patient = _make_patient(allergies=[])
        result = _make_result()
        brief = self.renderer.render(patient, result)
        assert "NKDA" in brief

    def test_fallback_when_template_missing(self, tmp_path, monkeypatch):
        """Renderer should fall back to result.clinician_brief if template is missing."""
        import src.core.brief_templates as bt

        monkeypatch.setattr(bt, "TEMPLATES_DIR", tmp_path)  # Empty dir — no template

        renderer = BriefRenderer()
        patient = _make_patient()
        result = _make_result()
        result.clinician_brief = "FALLBACK BRIEF CONTENT"

        brief = renderer.render(patient, result)
        assert "FALLBACK BRIEF CONTENT" in brief


# ---------------------------------------------------------------------------
# _build_reconciliation_rows helper tests
# ---------------------------------------------------------------------------


class TestBuildReconciliationRows:
    def test_maps_admission_and_discharge_doses(self):
        patient = _make_patient()
        recon = [
            ReconciliationEntry(
                medication="Warfarin",
                action=ReconciliationAction.CONTINUE,
                reason="Therapeutic INR",
            )
        ]
        rows = _build_reconciliation_rows(patient, recon)
        assert len(rows) == 1
        assert rows[0]["medication"] == "Warfarin"
        assert "5 mg" in rows[0]["admission_dose"]
        assert "5 mg" in rows[0]["discharge_dose"]

    def test_dash_when_med_not_in_list(self):
        patient = _make_patient()
        recon = [
            ReconciliationEntry(
                medication="UnknownDrug",
                action=ReconciliationAction.ADD,
                reason="New prescription",
            )
        ]
        rows = _build_reconciliation_rows(patient, recon)
        assert rows[0]["admission_dose"] == "—"
        assert rows[0]["discharge_dose"] == "—"

    def test_reason_truncated_at_120_chars(self):
        patient = _make_patient()
        long_reason = "A" * 200
        recon = [
            ReconciliationEntry(
                medication="Warfarin",
                action=ReconciliationAction.CONTINUE,
                reason=long_reason,
            )
        ]
        rows = _build_reconciliation_rows(patient, recon)
        assert len(rows[0]["reason"]) <= 120


# ---------------------------------------------------------------------------
# Prescribing Cascade section tests
# ---------------------------------------------------------------------------


class TestCascadeSection:
    def setup_method(self):
        self.renderer = BriefRenderer()

    def test_cascade_section_appears_when_cascades_present(self):
        patient = _make_patient()
        result = _make_result(cascades=[_make_cascade()])
        brief = self.renderer.render(patient, result)
        assert "Prescribing Cascade" in brief
        assert "Amlodipine" in brief

    def test_cascade_chain_displayed(self):
        patient = _make_patient()
        result = _make_result(cascades=[_make_cascade()])
        brief = self.renderer.render(patient, result)
        assert "Furosemide" in brief
        assert "Potassium Chloride" in brief

    def test_cascade_root_side_effect_displayed(self):
        patient = _make_patient()
        cascade = _make_cascade()
        result = _make_result(cascades=[cascade])
        brief = self.renderer.render(patient, result)
        assert "edema" in brief.lower() or "ankle" in brief.lower()

    def test_no_cascade_message_when_empty(self):
        patient = _make_patient()
        result = _make_result(cascades=[])
        brief = self.renderer.render(patient, result)
        assert "No prescribing cascades identified" in brief

    def test_cascade_count_in_summary_table(self):
        patient = _make_patient()
        result = _make_result(cascades=[_make_cascade(), _make_cascade()])
        brief = self.renderer.render(patient, result)
        assert "Prescribing Cascades Detected" in brief
        # 2 cascades should show "2" in the summary
        assert "| 2 |" in brief or "2" in brief

    def test_cascade_recommendation_shown(self):
        patient = _make_patient()
        cascade = _make_cascade()
        result = _make_result(cascades=[cascade])
        brief = self.renderer.render(patient, result)
        assert "non-CCB" in brief or "antihypertensive" in brief


# ---------------------------------------------------------------------------
# Patient brief renderer tests
# ---------------------------------------------------------------------------


class TestPatientBriefRenderer:
    def setup_method(self):
        self.renderer = PatientBriefRenderer()
        self.patient = _make_patient(name="Margaret Thompson", age=78)

    def _make_brief_data(self, **overrides) -> dict:
        base = {
            "greeting": "Welcome home, Margaret. Here is what you need to know.",
            "medications_continuing": [
                {"name": "Warfarin", "plain_name": "blood thinner", "why": "Keeps your blood from clotting too much"}
            ],
            "medications_stopped": [
                {"name": "Ibuprofen", "why_stopped": "This pain reliever can hurt your kidneys. Use Tylenol instead."}
            ],
            "medications_changed": [
                {"name": "Metformin", "what_changed": "Dose cut in half (500 mg twice a day)", "why": "To protect your kidneys"}
            ],
            "medications_new": [
                {"name": "Pantoprazole", "plain_name": "stomach acid reducer", "why": "Protects your stomach", "how_to_take": "Once daily in the morning"}
            ],
            "warning_signs": [
                {"sign": "Any unusual bleeding or large bruises", "action": "call your doctor immediately"},
                {"sign": "Chest pain or trouble breathing", "action": "call 911"},
            ],
            "important_dos_and_donts": [
                "Do NOT take ibuprofen, Advil, or Motrin",
                "Take Warfarin at the same time every day",
            ],
            "follow_up_reminder": "See your regular doctor within 7 days.",
        }
        base.update(overrides)
        return base

    def test_renders_without_crashing(self):
        brief = self.renderer.render(self.patient, self._make_brief_data())
        assert isinstance(brief, str)
        assert len(brief) > 100

    def test_patient_name_in_header(self):
        brief = self.renderer.render(self.patient, self._make_brief_data())
        assert "Margaret Thompson" in brief

    def test_stopped_medications_section(self):
        brief = self.renderer.render(self.patient, self._make_brief_data())
        assert "Ibuprofen" in brief
        assert "STOPPING" in brief or "Stopping" in brief

    def test_changed_medications_section(self):
        brief = self.renderer.render(self.patient, self._make_brief_data())
        assert "Metformin" in brief
        assert "CHANGING" in brief or "Changing" in brief

    def test_new_medications_section(self):
        brief = self.renderer.render(self.patient, self._make_brief_data())
        assert "Pantoprazole" in brief
        assert "NEW" in brief or "New" in brief

    def test_continuing_medications_section(self):
        brief = self.renderer.render(self.patient, self._make_brief_data())
        assert "Warfarin" in brief
        assert "CONTINUING" in brief or "Continuing" in brief

    def test_warning_signs_shown(self):
        brief = self.renderer.render(self.patient, self._make_brief_data())
        assert "bleeding" in brief.lower()
        assert "call 911" in brief.lower() or "911" in brief

    def test_dos_and_donts_shown(self):
        brief = self.renderer.render(self.patient, self._make_brief_data())
        assert "ibuprofen" in brief.lower() or "Advil" in brief

    def test_follow_up_reminder_shown(self):
        brief = self.renderer.render(self.patient, self._make_brief_data())
        assert "7 days" in brief

    def test_plain_english_signature(self):
        brief = self.renderer.render(self.patient, self._make_brief_data())
        assert "MedHarmony" in brief
        assert "doctor" in brief.lower()

    def test_empty_brief_data_does_not_crash(self):
        """Empty dict should fall through to template defaults gracefully."""
        brief = self.renderer.render(self.patient, {})
        assert isinstance(brief, str)
        assert "Margaret Thompson" in brief

    def test_fallback_when_template_missing(self, tmp_path, monkeypatch):
        import src.core.brief_templates as bt
        monkeypatch.setattr(bt, "TEMPLATES_DIR", tmp_path)
        renderer = PatientBriefRenderer()
        brief = renderer.render(self.patient, self._make_brief_data())
        assert "Margaret Thompson" in brief

    def test_plain_language_tone(self):
        """Brief should use plain words, not medical jargon in patient sections."""
        brief = self.renderer.render(self.patient, self._make_brief_data())
        # The patient brief should not contain raw clinical jargon in the data sections
        # (The brief_data dict is already plain English from the LLM)
        assert "blood thinner" in brief.lower() or "warfarin" in brief.lower()
        assert "kidney" in brief.lower()
