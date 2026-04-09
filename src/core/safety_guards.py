"""Safety guardrails for MedHarmony agent outputs.

Validates and sanitises agent outputs before returning them to the caller.
Ensures clinical safety standards are met and PHI is protected in error logs.
All guards are non-blocking — they log warnings and patch outputs rather than
raising exceptions, so a single guard failure never kills the whole response.
"""

from __future__ import annotations

import re
from typing import Optional

from loguru import logger

from src.models.medication import MedHarmonyResult, Severity


class SafetyGuards:
    """Final-pass validation of MedHarmony outputs before delivery.

    Call ``run_all(result)`` to apply every guard in one shot::

        result, warnings = SafetyGuards().run_all(result)
    """

    # PHI patterns → replacement tokens for safe log redaction
    _PHI_PATTERNS: list[tuple[re.Pattern, str]] = [
        (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
        (re.compile(r"\b\d{4}[-/]\d{2}[-/]\d{2}\b"), "[DATE]"),
        (re.compile(r"\bDOB?\s*:?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", re.I), "[DOB]"),
        (re.compile(r"\bMRN?\s*:?\s*[\w\d-]+", re.I), "[MRN]"),
        (re.compile(r"\b\d{10,11}\b"), "[PHONE]"),
        (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
        # Match "born MM/DD/YYYY" or similar
        (re.compile(r"\bborn\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", re.I), "born [DOB]"),
    ]

    _AUTONOMOUS_PHRASES = [
        "stop immediately",
        "discontinue immediately",
        "must stop",
        "never take",
        "do not take",
        "contraindicated — stop",
        "contraindicated -- stop",
        "contraindicated: stop",
    ]

    _CLINICIAN_FRAMING_PHRASES = [
        "for clinician review",
        "clinician should",
        "physician should",
        "prescriber should",
        "recommend to the clinician",
        "advise the clinician",
        "consult with",
        "discuss with",
        "clinician must review",
    ]

    # ------------------------------------------------------------------
    # Individual guards
    # ------------------------------------------------------------------

    def validate_no_autonomous_denials(self, result: MedHarmonyResult) -> MedHarmonyResult:
        """Append '(for clinician review)' to any recommendation that uses stop-medication
        language without appropriate clinician framing.
        """
        patched: list[str] = []

        for ix in result.interactions:
            rec_lower = ix.recommendation.lower()
            if any(p in rec_lower for p in self._AUTONOMOUS_PHRASES):
                if not any(f in rec_lower for f in self._CLINICIAN_FRAMING_PHRASES):
                    ix.recommendation += " (for clinician review)"
                    patched.append(f"interaction:{ix.drug_a}")

        for dep in result.deprescribing:
            rec_lower = dep.recommendation.lower()
            if any(p in rec_lower for p in self._AUTONOMOUS_PHRASES):
                if not any(f in rec_lower for f in self._CLINICIAN_FRAMING_PHRASES):
                    dep.recommendation += " (for clinician review)"
                    patched.append(f"deprescribing:{dep.medication}")

        if patched:
            logger.warning(
                f"SafetyGuards[no_autonomous_denials]: added clinician framing to "
                f"{len(patched)} recommendations: {patched}"
            )
        return result

    def validate_evidence_citations(self, result: MedHarmonyResult) -> MedHarmonyResult:
        """Ensure every CRITICAL/HIGH interaction has an evidence_source field.
        Inserts a placeholder if missing so the brief always shows a citation.
        """
        uncited: list[str] = []

        for ix in result.interactions:
            if ix.severity in (Severity.CRITICAL, Severity.HIGH) and not ix.evidence_source:
                ix.evidence_source = (
                    "Clinical judgment — verify against current FDA labeling and guidelines"
                )
                uncited.append(ix.drug_a)

        if uncited:
            logger.warning(
                f"SafetyGuards[evidence_citations]: added placeholder citations for "
                f"{len(uncited)} high/critical interactions: {uncited}"
            )
        return result

    def validate_severity_consistency(self, result: MedHarmonyResult) -> MedHarmonyResult:
        """Ensure every CRITICAL finding has a non-empty actionable recommendation.
        Inserts a generic urgent-review recommendation if one is missing.
        """
        patched: list[str] = []

        for ix in result.interactions:
            if ix.severity == Severity.CRITICAL and not ix.recommendation.strip():
                ix.recommendation = (
                    "CRITICAL: Immediate clinician review required. "
                    "Assess risk/benefit and consider alternative therapy."
                )
                patched.append(f"interaction:{ix.drug_a}")

        for dep in result.deprescribing:
            if dep.severity == Severity.CRITICAL and not dep.recommendation.strip():
                dep.recommendation = (
                    "CRITICAL: Immediate review recommended per clinical guidelines. "
                    "Discuss with prescribing clinician before next dose."
                )
                patched.append(f"deprescribing:{dep.medication}")

        if patched:
            logger.warning(
                f"SafetyGuards[severity_consistency]: added recommendations to "
                f"{len(patched)} critical findings: {patched}"
            )
        return result

    # ------------------------------------------------------------------
    # PHI redaction
    # ------------------------------------------------------------------

    def redact_phi(self, text: str) -> str:
        """Redact common PHI patterns from *text* for safe logging.

        Handles SSNs, dates of birth, MRNs, phone numbers, and email addresses.
        This is a best-effort heuristic — it should NOT be the sole PHI control.
        """
        for pattern, replacement in self._PHI_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    # ------------------------------------------------------------------
    # Composite runner
    # ------------------------------------------------------------------

    def run_all(self, result: MedHarmonyResult) -> tuple[MedHarmonyResult, list[str]]:
        """Apply all safety guards in sequence.

        Returns:
            (patched_result, warnings) where *warnings* is a list of any guard
            method that raised an unexpected exception (guards never crash the caller).
        """
        warnings: list[str] = []

        guards = [
            ("validate_no_autonomous_denials", self.validate_no_autonomous_denials),
            ("validate_evidence_citations", self.validate_evidence_citations),
            ("validate_severity_consistency", self.validate_severity_consistency),
        ]

        for name, guard in guards:
            try:
                result = guard(result)
            except Exception as exc:
                msg = f"{name} raised {type(exc).__name__}: {exc}"
                warnings.append(msg)
                logger.error(f"SafetyGuards: {msg}")

        return result, warnings
