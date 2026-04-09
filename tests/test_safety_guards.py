"""Unit tests for SafetyGuards.

Tests each guard method independently and verifies PHI redaction works
on common patterns. No network calls — fully offline.
"""

from __future__ import annotations

import pytest

from src.core.safety_guards import SafetyGuards
from src.models.medication import (
    DeprescribingRecommendation,
    DrugInteraction,
    InteractionType,
    MedHarmonyResult,
    ReconciliationEntry,
    ReconciliationAction,
    Severity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(interactions=None, deprescribing=None) -> MedHarmonyResult:
    return MedHarmonyResult(
        patient_id="test-001",
        patient_name="Test Patient",
        reconciliation=[] if not None else [],
        interactions=interactions or [],
        deprescribing=deprescribing or [],
        total_medications=5,
        critical_issues=0,
        high_issues=0,
        moderate_issues=0,
        clinician_brief="",
    )


def _make_interaction(
    severity=Severity.CRITICAL,
    recommendation="Stop immediately",
    evidence_source=None,
) -> DrugInteraction:
    return DrugInteraction(
        type=InteractionType.DRUG_DRUG,
        severity=severity,
        drug_a="Warfarin",
        drug_b="Ibuprofen",
        description="Increased bleeding risk",
        clinical_significance="High bleed risk",
        recommendation=recommendation,
        evidence_source=evidence_source,
    )


def _make_deprescribing(
    severity=Severity.CRITICAL,
    recommendation="Stop immediately",
) -> DeprescribingRecommendation:
    return DeprescribingRecommendation(
        medication="Diazepam",
        criteria="Beers Criteria 2023",
        reason="Falls risk in elderly",
        recommendation=recommendation,
        severity=severity,
    )


# ---------------------------------------------------------------------------
# validate_no_autonomous_denials
# ---------------------------------------------------------------------------


class TestValidateNoAutonomousDenials:
    def test_adds_framing_to_stop_immediately(self):
        ix = _make_interaction(recommendation="Stop immediately and do not restart")
        result = _make_result(interactions=[ix])
        guards = SafetyGuards()
        result = guards.validate_no_autonomous_denials(result)
        assert "for clinician review" in result.interactions[0].recommendation.lower()

    def test_does_not_double_add_framing(self):
        ix = _make_interaction(
            recommendation="Stop immediately — for clinician review"
        )
        result = _make_result(interactions=[ix])
        guards = SafetyGuards()
        result = guards.validate_no_autonomous_denials(result)
        # Should NOT add a second "(for clinician review)"
        rec = result.interactions[0].recommendation
        assert rec.lower().count("for clinician review") == 1

    def test_safe_recommendation_untouched(self):
        ix = _make_interaction(recommendation="Monitor INR weekly and adjust dose as needed")
        original_rec = ix.recommendation
        result = _make_result(interactions=[ix])
        guards = SafetyGuards()
        result = guards.validate_no_autonomous_denials(result)
        assert result.interactions[0].recommendation == original_rec

    def test_deprescribing_also_checked(self):
        dep = _make_deprescribing(recommendation="Must stop this medication at once")
        result = _make_result(deprescribing=[dep])
        guards = SafetyGuards()
        result = guards.validate_no_autonomous_denials(result)
        assert "for clinician review" in result.deprescribing[0].recommendation.lower()

    def test_do_not_take_phrase(self):
        ix = _make_interaction(recommendation="Do not take warfarin with NSAIDs")
        result = _make_result(interactions=[ix])
        guards = SafetyGuards()
        result = guards.validate_no_autonomous_denials(result)
        assert "for clinician review" in result.interactions[0].recommendation.lower()


# ---------------------------------------------------------------------------
# validate_evidence_citations
# ---------------------------------------------------------------------------


class TestValidateEvidenceCitations:
    def test_adds_placeholder_for_critical_without_citation(self):
        ix = _make_interaction(severity=Severity.CRITICAL, evidence_source=None)
        result = _make_result(interactions=[ix])
        guards = SafetyGuards()
        result = guards.validate_evidence_citations(result)
        assert result.interactions[0].evidence_source is not None
        assert len(result.interactions[0].evidence_source) > 0

    def test_adds_placeholder_for_high_without_citation(self):
        ix = _make_interaction(severity=Severity.HIGH, evidence_source=None)
        result = _make_result(interactions=[ix])
        guards = SafetyGuards()
        result = guards.validate_evidence_citations(result)
        assert result.interactions[0].evidence_source is not None

    def test_does_not_overwrite_existing_citation(self):
        ix = _make_interaction(
            severity=Severity.CRITICAL,
            evidence_source="Beers Criteria 2023",
        )
        result = _make_result(interactions=[ix])
        guards = SafetyGuards()
        result = guards.validate_evidence_citations(result)
        assert result.interactions[0].evidence_source == "Beers Criteria 2023"

    def test_moderate_interaction_without_citation_not_changed(self):
        ix = _make_interaction(severity=Severity.MODERATE, evidence_source=None)
        result = _make_result(interactions=[ix])
        guards = SafetyGuards()
        result = guards.validate_evidence_citations(result)
        # Moderate interactions are not required to have citations
        assert result.interactions[0].evidence_source is None


# ---------------------------------------------------------------------------
# validate_severity_consistency
# ---------------------------------------------------------------------------


class TestValidateSeverityConsistency:
    def test_adds_recommendation_to_critical_with_empty(self):
        ix = _make_interaction(severity=Severity.CRITICAL, recommendation="")
        result = _make_result(interactions=[ix])
        guards = SafetyGuards()
        result = guards.validate_severity_consistency(result)
        assert result.interactions[0].recommendation.strip() != ""
        assert "clinician" in result.interactions[0].recommendation.lower()

    def test_adds_recommendation_to_critical_deprescribing(self):
        dep = _make_deprescribing(severity=Severity.CRITICAL, recommendation="  ")
        result = _make_result(deprescribing=[dep])
        guards = SafetyGuards()
        result = guards.validate_severity_consistency(result)
        assert result.deprescribing[0].recommendation.strip() != ""

    def test_non_critical_with_empty_rec_not_patched(self):
        ix = _make_interaction(severity=Severity.MODERATE, recommendation="")
        result = _make_result(interactions=[ix])
        guards = SafetyGuards()
        result = guards.validate_severity_consistency(result)
        # Moderate empty recs are not auto-patched
        assert result.interactions[0].recommendation == ""

    def test_critical_with_existing_rec_not_overwritten(self):
        ix = _make_interaction(
            severity=Severity.CRITICAL,
            recommendation="Consult cardiology immediately",
        )
        result = _make_result(interactions=[ix])
        guards = SafetyGuards()
        result = guards.validate_severity_consistency(result)
        assert result.interactions[0].recommendation == "Consult cardiology immediately"


# ---------------------------------------------------------------------------
# redact_phi
# ---------------------------------------------------------------------------


class TestRedactPhi:
    def setup_method(self):
        self.guards = SafetyGuards()

    def test_redacts_ssn(self):
        text = "Patient SSN is 123-45-6789, please verify"
        redacted = self.guards.redact_phi(text)
        assert "123-45-6789" not in redacted
        assert "[SSN]" in redacted

    def test_redacts_dob_format(self):
        text = "DOB: 01/15/1946 — elderly patient"
        redacted = self.guards.redact_phi(text)
        assert "01/15/1946" not in redacted

    def test_redacts_mrn(self):
        text = "MRN: 12345678 was used for this patient"
        redacted = self.guards.redact_phi(text)
        assert "12345678" not in redacted
        assert "[MRN]" in redacted

    def test_redacts_email(self):
        text = "Contact patient at margaret.thompson@hospital.com"
        redacted = self.guards.redact_phi(text)
        assert "margaret.thompson@hospital.com" not in redacted
        assert "[EMAIL]" in redacted

    def test_safe_text_unchanged(self):
        text = "Patient has CKD Stage 3b with eGFR 32 mL/min"
        redacted = self.guards.redact_phi(text)
        assert redacted == text

    def test_phone_number_redacted(self):
        text = "Callback number: 5551234567 for patient"
        redacted = self.guards.redact_phi(text)
        assert "5551234567" not in redacted


# ---------------------------------------------------------------------------
# run_all
# ---------------------------------------------------------------------------


class TestRunAll:
    def test_run_all_returns_result_and_warnings(self):
        result = _make_result(
            interactions=[_make_interaction(recommendation="Stop immediately")],
        )
        guards = SafetyGuards()
        patched, warnings = guards.run_all(result)
        assert isinstance(patched, MedHarmonyResult)
        assert isinstance(warnings, list)

    def test_run_all_applies_all_three_guards(self):
        ix = DrugInteraction(
            type=InteractionType.DRUG_DRUG,
            severity=Severity.CRITICAL,
            drug_a="DrugA",
            description="Test",
            clinical_significance="Test",
            recommendation="",  # Empty → severity_consistency should patch
            evidence_source=None,  # Missing → evidence_citations should patch
        )
        result = _make_result(interactions=[ix])
        guards = SafetyGuards()
        patched, warnings = guards.run_all(result)

        assert patched.interactions[0].recommendation.strip() != ""
        assert patched.interactions[0].evidence_source is not None
        assert warnings == []  # No guard errors expected
