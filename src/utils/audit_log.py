"""HIPAA-style audit logging for MedHarmony.

Logs every patient data access event to a structured JSONL file that rotates daily.
Write failures are caught and logged — they must never crash the agent.

Every entry contains:
  timestamp, patient_id, user_role, action, accessed_resources,
  agent_id, organization_id, outcome, compliance_standard
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger


class AuditLog:
    """HIPAA-style patient data access auditor.

    Usage::

        audit = AuditLog()
        audit.log_access(
            patient_id="pt-12345",
            user_role="pharmacist",
            action="medication_reconciliation",
            accessed_resources=["Patient", "MedicationRequest", "Condition"],
        )
    """

    def __init__(self, log_dir: Optional[Path] = None) -> None:
        if log_dir is None:
            from src.agent.config import PROJECT_ROOT

            log_dir = PROJECT_ROOT / "logs" / "audit"
        self.log_dir = Path(log_dir)
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error(f"AuditLog: cannot create log directory {self.log_dir}: {exc}")

    def _get_log_path(self) -> Path:
        """Return today's JSONL file path (one file per UTC day)."""
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.log_dir / f"audit_{date_str}.jsonl"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_access(
        self,
        patient_id: str,
        user_role: str,
        action: str,
        accessed_resources: list[str],
        agent_id: str = "medharmony-agent",
        organization_id: Optional[str] = None,
        outcome: str = "success",
    ) -> None:
        """Record a successful (or attempted) patient data access event."""
        self._write(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": "patient_data_access",
                "patient_id": patient_id,
                "user_role": user_role,
                "action": action,
                "accessed_resources": accessed_resources,
                "agent_id": agent_id,
                "organization_id": organization_id,
                "outcome": outcome,
                "compliance_standard": "HIPAA",
            }
        )

    def log_error(
        self,
        patient_id: str,
        action: str,
        error_message: str,
        agent_id: str = "medharmony-agent",
    ) -> None:
        """Record a failed data access attempt (e.g. FHIR pull error)."""
        # Truncate error message to avoid logging sensitive stack traces
        safe_error = error_message[:200] if error_message else "unknown error"
        self.log_access(
            patient_id=patient_id,
            user_role="system",
            action=action,
            accessed_resources=[],
            agent_id=agent_id,
            outcome=f"error: {safe_error}",
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write(self, entry: dict) -> None:
        try:
            with open(self._get_log_path(), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError as exc:
            # A write failure must never crash the agent — just warn
            logger.warning(f"AuditLog: write failed ({exc}). Entry: {entry.get('action')}")
