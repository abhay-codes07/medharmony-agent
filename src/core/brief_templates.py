"""Jinja2-based template rendering for MedHarmony clinician briefs.

Produces consistently formatted, professional clinical briefs by rendering
structured analysis data through the clinician_brief.md.j2 template.
This replaces freeform LLM markdown generation with deterministic layout.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateNotFound
from loguru import logger

from src.agent.config import DATA_DIR
from src.models.medication import (
    DeprescribingRecommendation,
    DrugInteraction,
    MedHarmonyResult,
    PatientContext,
    PrescribingCascade,
    ReconciliationEntry,
    Severity,
)


TEMPLATES_DIR = DATA_DIR / "templates"


# ---------------------------------------------------------------------------
# Jinja2 filters
# ---------------------------------------------------------------------------


def _severity_emoji(severity) -> str:
    val = severity.value if hasattr(severity, "value") else str(severity)
    return {"critical": "🔴", "high": "🟠", "moderate": "🟡", "low": "🟢"}.get(
        val.lower(), "⚪"
    )


def _action_emoji(action: str) -> str:
    return {
        "continue": "✅",
        "discontinue": "🛑",
        "modify-dose": "✏️",
        "substitute": "🔄",
        "add": "➕",
        "hold": "⏸️",
        "review": "🔍",
    }.get(action.lower(), "❓")


def _type_label(interaction_type) -> str:
    val = interaction_type.value if hasattr(interaction_type, "value") else str(interaction_type)
    return val.replace("-", " ").title()


# ---------------------------------------------------------------------------
# Helper — build reconciliation table rows
# ---------------------------------------------------------------------------


def _build_reconciliation_rows(
    patient_ctx: PatientContext,
    reconciliation: list[ReconciliationEntry],
) -> list[dict]:
    """Build structured rows for the reconciliation summary table."""
    admission_doses: dict[str, str] = {}
    discharge_doses: dict[str, str] = {}

    for ml in patient_ctx.medication_lists:
        for med in ml.medications:
            key = med.name.lower()
            dose_str = f"{med.dose} {med.frequency}".strip() if med.frequency else med.dose
            src = ml.source.lower()
            if "admission" in src or "home" in src:
                admission_doses[key] = dose_str
            elif "discharge" in src:
                discharge_doses[key] = dose_str

    rows = []
    for entry in reconciliation:
        key = entry.medication.lower()
        rows.append(
            {
                "medication": entry.medication,
                "admission_dose": admission_doses.get(key, "—"),
                "discharge_dose": discharge_doses.get(key, "—"),
                "action": entry.action.value,
                "reason": (entry.reason or "—")[:120],
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------


class BriefRenderer:
    """Renders MedHarmony clinician briefs through a Jinja2 template.

    Falls back to the raw LLM brief stored in ``result.clinician_brief``
    if the template cannot be loaded or rendered.

    Usage::

        renderer = BriefRenderer()
        markdown = renderer.render(patient_ctx, result)
    """

    def __init__(self) -> None:
        try:
            self._env = Environment(
                loader=FileSystemLoader(str(TEMPLATES_DIR)),
                autoescape=select_autoescape(["html"]),
                trim_blocks=True,
                lstrip_blocks=True,
            )
            self._env.filters["severity_emoji"] = _severity_emoji
            self._env.filters["action_emoji"] = _action_emoji
            self._env.filters["type_label"] = _type_label
        except Exception as exc:
            logger.error(f"BriefRenderer: failed to initialise Jinja2 env: {exc}")
            self._env = None  # type: ignore[assignment]

    def render(
        self,
        patient_ctx: PatientContext,
        result: MedHarmonyResult,
        clinician_name: str = "Attending Clinician",
    ) -> str:
        """Render the full clinician brief.

        Args:
            patient_ctx: Full patient context (demographics, labs, meds).
            result: The assembled MedHarmonyResult (reconciliation, interactions, deprescribing).
            clinician_name: Name printed in the brief's signature line.

        Returns:
            Rendered Markdown string.
        """
        if self._env is None:
            return result.clinician_brief or "Brief rendering failed: template engine unavailable."

        try:
            template = self._env.get_template("clinician_brief.md.j2")
        except TemplateNotFound:
            logger.warning("BriefRenderer: clinician_brief.md.j2 not found — using LLM fallback")
            return result.clinician_brief or "Brief template not found."
        except Exception as exc:
            logger.error(f"BriefRenderer: template load failed: {exc}")
            return result.clinician_brief or f"Brief rendering failed: {exc}"

        # ----------------------------------------------------------------
        # Build template context
        # ----------------------------------------------------------------

        # Extract key lab values
        egfr: Optional[float] = next(
            (lr.value for lr in patient_ctx.lab_results if "egfr" in lr.name.lower()),
            None,
        )
        inr: Optional[float] = next(
            (lr.value for lr in patient_ctx.lab_results if lr.name.upper() == "INR"),
            None,
        )
        creatinine: Optional[float] = next(
            (lr.value for lr in patient_ctx.lab_results if "creatinine" in lr.name.lower()),
            None,
        )

        # Group interactions by severity string for template iteration
        interactions_by_severity: dict[str, list[DrugInteraction]] = {
            "critical": [],
            "high": [],
            "moderate": [],
            "low": [],
        }
        for ix in result.interactions:
            key = ix.severity.value if hasattr(ix.severity, "value") else str(ix.severity)
            interactions_by_severity.setdefault(key, []).append(ix)

        # Reconciliation table rows
        recon_rows = _build_reconciliation_rows(patient_ctx, result.reconciliation)

        # Summary stats
        summary_stats = {
            "total_medications": result.total_medications,
            "critical_issues": result.critical_issues,
            "high_issues": result.high_issues,
            "moderate_issues": result.moderate_issues,
            "reconciliation_changes": sum(
                1 for r in result.reconciliation if r.action.value != "continue"
            ),
            "deprescribing_candidates": len(result.deprescribing),
        }

        # Add cascade count to summary
        summary_stats["prescribing_cascades"] = len(result.prescribing_cascades)

        context = {
            "patient": patient_ctx,
            "result": result,
            "egfr": egfr,
            "inr": inr,
            "creatinine": creatinine,
            "allergies_str": (
                ", ".join(a.substance for a in patient_ctx.allergies) or "NKDA"
            ),
            "interactions_by_severity": interactions_by_severity,
            "recon_rows": recon_rows,
            "summary_stats": summary_stats,
            "clinician_name": clinician_name,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "has_critical": result.critical_issues > 0,
            "has_interactions": bool(result.interactions),
            "has_deprescribing": bool(result.deprescribing),
        }

        try:
            return template.render(**context)
        except Exception as exc:
            logger.error(f"BriefRenderer: template render failed: {exc}")
            return result.clinician_brief or f"Brief rendering failed: {exc}"


# ---------------------------------------------------------------------------
# Patient-facing brief renderer
# ---------------------------------------------------------------------------


class PatientBriefRenderer:
    """Renders a plain-language patient discharge brief via patient_brief.md.j2.

    The template is written at an 8th-grade reading level and explains what
    changed in the patient's medications, warning signs to watch for, and
    when to call their doctor.

    The ``brief_data`` dict is generated by
    ``LLMClient.generate_patient_brief_data()`` and contains:
      - greeting, medications_continuing, medications_stopped,
        medications_changed, medications_new, warning_signs,
        important_dos_and_donts, follow_up_reminder

    Usage::

        renderer = PatientBriefRenderer()
        markdown = renderer.render(patient_ctx, brief_data)
    """

    def __init__(self) -> None:
        try:
            self._env = Environment(
                loader=FileSystemLoader(str(TEMPLATES_DIR)),
                autoescape=select_autoescape(["html"]),
                trim_blocks=True,
                lstrip_blocks=True,
            )
        except Exception as exc:
            logger.error(f"PatientBriefRenderer: failed to init Jinja2 env: {exc}")
            self._env = None  # type: ignore[assignment]

    def render(
        self,
        patient_ctx: PatientContext,
        brief_data: dict,
        clinician_name: str = "Your Care Team",
    ) -> str:
        """Render the patient-facing discharge brief.

        Args:
            patient_ctx: Patient demographics and medication context.
            brief_data: Structured dict from LLMClient.generate_patient_brief_data().
            clinician_name: Name/role printed in the footer.

        Returns:
            Plain-language Markdown string suitable for printing or display.
        """
        if self._env is None:
            return self._fallback(patient_ctx)

        try:
            template = self._env.get_template("patient_brief.md.j2")
        except TemplateNotFound:
            logger.warning("PatientBriefRenderer: patient_brief.md.j2 not found")
            return self._fallback(patient_ctx)
        except Exception as exc:
            logger.error(f"PatientBriefRenderer: template load failed: {exc}")
            return self._fallback(patient_ctx)

        context = {
            "patient": patient_ctx,
            "brief_data": brief_data or {},
            "clinician_name": clinician_name,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        }

        try:
            return template.render(**context)
        except Exception as exc:
            logger.error(f"PatientBriefRenderer: render failed: {exc}")
            return self._fallback(patient_ctx)

    @staticmethod
    def _fallback(patient_ctx: PatientContext) -> str:
        name = patient_ctx.name or "Patient"
        return (
            f"# Your Medication Information\n\n"
            f"Dear {name},\n\n"
            "Please review your discharge paperwork for your updated medication list.\n"
            "If you have questions about your medications, call your care team.\n\n"
            "*Generated by MedHarmony*"
        )
