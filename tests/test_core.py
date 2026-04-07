"""Tests for MedHarmony Agent."""

import pytest
from src.models.medication import (
    Medication,
    MedicationList,
    PatientContext,
    Allergy,
    Condition,
    LabResult,
    SharpContext,
    MedHarmonyResult,
    Severity,
)
from src.utils.sharp_context import extract_sharp_context, build_sharp_response_metadata
from src.agent.agent_card import get_agent_card


# =============================================================================
# Model Tests
# =============================================================================

class TestModels:
    def test_medication_creation(self):
        med = Medication(name="Metformin", dose="500 mg", frequency="twice daily")
        assert med.name == "Metformin"
        assert med.status == "active"

    def test_patient_context(self):
        ctx = PatientContext(
            patient_id="test-001",
            name="Test Patient",
            age=75,
            sex="male",
        )
        assert ctx.patient_id == "test-001"
        assert ctx.allergies == []
        assert ctx.medication_lists == []

    def test_medication_list(self):
        ml = MedicationList(
            source="admission",
            medications=[
                Medication(name="Aspirin", dose="81 mg"),
                Medication(name="Lisinopril", dose="10 mg"),
            ],
        )
        assert len(ml.medications) == 2

    def test_result_model(self):
        result = MedHarmonyResult(
            patient_id="test-001",
            total_medications=5,
            critical_issues=1,
            high_issues=2,
            moderate_issues=1,
        )
        assert result.critical_issues == 1
        assert result.clinician_brief == ""


# =============================================================================
# SHARP Context Tests
# =============================================================================

class TestSharpContext:
    def test_extract_from_sharp_key(self):
        metadata = {
            "sharp": {
                "patient_id": "patient-123",
                "fhir_server_url": "https://fhir.example.com/R4",
                "fhir_access_token": "token-abc",
            }
        }
        ctx = extract_sharp_context(metadata)
        assert ctx.patient_id == "patient-123"
        assert ctx.fhir_server_url == "https://fhir.example.com/R4"
        assert ctx.fhir_access_token == "token-abc"

    def test_extract_from_flat_keys(self):
        metadata = {
            "patient_id": "patient-456",
            "fhir_server_url": "https://fhir2.example.com/R4",
        }
        ctx = extract_sharp_context(metadata)
        assert ctx.patient_id == "patient-456"

    def test_extract_from_fhir_context(self):
        metadata = {
            "fhirContext": [
                {"reference": "Patient/patient-789"},
                {"reference": "Encounter/enc-001"},
            ]
        }
        ctx = extract_sharp_context(metadata)
        assert ctx.patient_id == "patient-789"
        assert ctx.encounter_id == "enc-001"

    def test_extract_empty_metadata(self):
        ctx = extract_sharp_context({})
        assert ctx.patient_id is None

    def test_build_response_metadata(self):
        ctx = SharpContext(
            patient_id="p-001",
            fhir_server_url="https://fhir.example.com",
            encounter_id="enc-001",
        )
        meta = build_sharp_response_metadata(ctx)
        assert meta["sharp"]["patient_id"] == "p-001"


# =============================================================================
# Agent Card Tests
# =============================================================================

class TestAgentCard:
    def test_agent_card_structure(self):
        card = get_agent_card()
        assert card["name"] == "MedHarmony"
        assert "skills" in card
        assert len(card["skills"]) == 4

    def test_agent_card_skills(self):
        card = get_agent_card()
        skill_ids = [s["id"] for s in card["skills"]]
        assert "medication-reconciliation" in skill_ids
        assert "drug-interaction-analysis" in skill_ids
        assert "deprescribing-advisor" in skill_ids
        assert "clinician-safety-brief" in skill_ids

    def test_agent_card_sharp_extension(self):
        card = get_agent_card()
        sharp = card["extensions"]["sharp"]
        assert sharp["supportsPatientContext"] is True
        assert "MedicationRequest" in sharp["requiredFhirResources"]
        assert sharp["fhirVersion"] == "R4"


# =============================================================================
# Demo Patient Tests
# =============================================================================

class TestDemoPatient:
    def test_demo_patient_has_dangerous_combos(self):
        """The demo patient should have intentionally dangerous medication combos
        that MedHarmony should catch."""
        from src.core.reconciliation import ReconciliationEngine
        engine = ReconciliationEngine()
        patient = engine._get_demo_patient_context("demo-001")

        assert patient.name == "Margaret Thompson"
        assert patient.age == 78

        # Should have CKD (eGFR 32)
        egfr = next((l for l in patient.lab_results if l.name == "eGFR"), None)
        assert egfr is not None
        assert egfr.value == 32.0

        # Should be on ibuprofen (NSAID) — dangerous with CKD + warfarin
        all_meds = []
        for ml in patient.medication_lists:
            all_meds.extend([m.name.lower() for m in ml.medications])
        assert any("ibuprofen" in m for m in all_meds)

        # Should be on warfarin + potentially apixaban (dual anticoagulant risk)
        assert any("warfarin" in m for m in all_meds)

        # Should be on diazepam (Beers Criteria for elderly)
        assert any("diazepam" in m for m in all_meds)

        # Should be on diphenhydramine (Beers Criteria — anticholinergic)
        assert any("diphenhydramine" in m for m in all_meds)

        # Should have high potassium
        potassium = next((l for l in patient.lab_results if l.name == "Potassium"), None)
        assert potassium is not None
        assert potassium.value > 5.0

    def test_demo_has_reconciliation_discrepancies(self):
        """Demo patient should have differences between admission and discharge lists."""
        from src.core.reconciliation import ReconciliationEngine
        engine = ReconciliationEngine()
        patient = engine._get_demo_patient_context("demo-001")

        admission_meds = set()
        discharge_meds = set()
        for ml in patient.medication_lists:
            for m in ml.medications:
                if ml.source == "admission_home_meds":
                    admission_meds.add(m.name.lower())
                elif ml.source == "discharge_medications":
                    discharge_meds.add(m.name.lower())

        # There should be meds in admission not in discharge (and vice versa)
        only_admission = admission_meds - discharge_meds
        only_discharge = discharge_meds - admission_meds
        assert len(only_admission) > 0, "Should have meds dropped at discharge"
        assert len(only_discharge) > 0, "Should have new meds at discharge"
