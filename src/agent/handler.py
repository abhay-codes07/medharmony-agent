"""A2A Task Handler for MedHarmony.

Processes incoming A2A tasks, extracts SHARP context,
routes to the reconciliation engine, and formats responses.

Week 3 additions:
- Reasoning trace included as a third A2A artifact
- medharmony.reasoning_trace_url in metadata
- Structured error artifact with trace on failure
- AuditLog for all incoming tasks
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from loguru import logger

from src.core.reconciliation import ReconciliationEngine
from src.models.medication import SharpContext
from src.utils.audit_log import AuditLog
from src.utils.sharp_context import build_sharp_response_metadata, extract_sharp_context


class TaskHandler:
    """Handles A2A tasks for the MedHarmony agent."""

    def __init__(self):
        self.engine = ReconciliationEngine()
        self.tasks: dict[str, dict] = {}  # In-memory task store
        self._audit = AuditLog()

    async def handle_task(self, task_request: dict) -> dict:
        """Process an incoming A2A task request.

        Returns a completed A2A task with three artifacts:
          1. clinician_safety_brief (Markdown)
          2. analysis_data (structured JSON)
          3. reasoning_trace (agent loop observability)
        """
        task_id = task_request.get("id", str(uuid.uuid4()))
        messages = task_request.get("messages", [])
        metadata = task_request.get("metadata", {})

        logger.info(f"Received task: {task_id}")

        # Extract SHARP context from multiple locations
        sharp_context = extract_sharp_context(metadata)

        # Also check message parts for SHARP data
        if not sharp_context.patient_id and messages:
            for msg in messages:
                for part in msg.get("parts", []):
                    if part.get("type") == "data":
                        data = part.get("data", {})
                        sharp_ctx = extract_sharp_context(data)
                        if sharp_ctx.patient_id:
                            sharp_context = sharp_ctx
                            break

        # Extract user message text
        user_message = ""
        for msg in messages:
            if msg.get("role") == "user":
                for part in msg.get("parts", []):
                    if part.get("type") == "text":
                        user_message = part.get("text", "")

        # Try to extract patient_id from message text as last resort
        if not sharp_context.patient_id and user_message:
            match = re.search(r"patient[_\s\-]?(?:id)?[:\s]+(\S+)", user_message, re.I)
            if match:
                sharp_context.patient_id = match.group(1)

        skill = self._determine_skill(user_message)
        logger.info(f"Invoking skill: {skill}")

        # Audit the incoming task
        self._audit.log_access(
            patient_id=sharp_context.patient_id or "unknown",
            user_role=sharp_context.user_role or "system",
            action=f"a2a_task:{skill}",
            accessed_resources=["A2A"],
        )

        # Update task status to working
        self.tasks[task_id] = {
            "id": task_id,
            "status": "working",
            "messages": messages,
            "metadata": metadata,
        }

        try:
            result = await self.engine.run_full_analysis(
                sharp_context=sharp_context,
                user_message=user_message,
            )

            # Build the trace URL (placeholder — real URL would be set post-deploy)
            agent_url = metadata.get("agent_url", "")
            trace_url = f"{agent_url}/tasks/{task_id}/trace" if agent_url else None

            response_task = {
                "id": task_id,
                "status": "completed",
                "messages": messages + [
                    {
                        "role": "agent",
                        "parts": [
                            {
                                "type": "text",
                                "text": self._build_response_text(result),
                            }
                        ],
                    }
                ],
                "artifacts": [
                    # Artifact 1: Clinician Brief (Markdown — rendered via Jinja2)
                    {
                        "name": "clinician_safety_brief",
                        "description": "MedHarmony Clinician Safety Brief (Jinja2-rendered)",
                        "parts": [
                            {
                                "type": "text",
                                "text": result.clinician_brief,
                                "metadata": {"mimeType": "text/markdown"},
                            }
                        ],
                    },
                    # Artifact 2: Structured analysis data (JSON)
                    {
                        "name": "analysis_data",
                        "description": "Structured medication analysis data (JSON)",
                        "parts": [
                            {
                                "type": "data",
                                "data": result.model_dump(exclude={"reasoning_trace"}),
                                "metadata": {"mimeType": "application/json"},
                            }
                        ],
                    },
                    # Artifact 3: Reasoning trace (Week 3 — full observability)
                    {
                        "name": "reasoning_trace",
                        "description": (
                            "MedHarmony agent reasoning trace — "
                            "every LLM call, tool call, and pipeline step"
                        ),
                        "parts": [
                            {
                                "type": "data",
                                "data": result.reasoning_trace or {},
                                "metadata": {"mimeType": "application/json"},
                            }
                        ],
                    },
                ],
                "metadata": {
                    **build_sharp_response_metadata(sharp_context),
                    "medharmony": {
                        "total_medications": result.total_medications,
                        "critical_issues": result.critical_issues,
                        "high_issues": result.high_issues,
                        "moderate_issues": result.moderate_issues,
                        "tasks_generated": len(result.tasks),
                        "reasoning_trace_steps": (
                            result.reasoning_trace.get("step_count", 0)
                            if result.reasoning_trace
                            else 0
                        ),
                        "reasoning_trace_url": trace_url,
                        "safety_warnings": result.safety_warnings,
                        "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                },
            }

            self.tasks[task_id] = response_task
            logger.info(f"Task {task_id} completed successfully")
            return response_task

        except Exception as exc:
            logger.error(f"Task {task_id} failed: {exc}")

            error_task = {
                "id": task_id,
                "status": "failed",
                "messages": messages + [
                    {
                        "role": "agent",
                        "parts": [
                            {
                                "type": "text",
                                "text": (
                                    f"MedHarmony analysis failed: {str(exc)}. "
                                    f"Please ensure a valid patient ID is provided "
                                    f"in the SHARP context."
                                ),
                            }
                        ],
                    }
                ],
                "artifacts": [
                    {
                        "name": "error_details",
                        "description": "Error information for debugging",
                        "parts": [
                            {
                                "type": "data",
                                "data": {
                                    "error": str(exc),
                                    "task_id": task_id,
                                    "patient_id": sharp_context.patient_id,
                                },
                                "metadata": {"mimeType": "application/json"},
                            }
                        ],
                    }
                ],
                "metadata": {
                    **metadata,
                    "medharmony": {
                        "error": str(exc),
                        "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                },
            }
            self.tasks[task_id] = error_task
            return error_task

    def _determine_skill(self, message: str) -> str:
        """Determine which skill to invoke based on the user message."""
        message_lower = message.lower()

        if any(kw in message_lower for kw in ["interaction", "contraindic", "allergy"]):
            return "drug-interaction-analysis"
        elif any(kw in message_lower for kw in ["deprescrib", "beers", "stopp", "polypharm"]):
            return "deprescribing-advisor"
        elif any(kw in message_lower for kw in ["brief", "summary", "report"]):
            return "clinician-safety-brief"
        else:
            return "full-analysis"

    def _build_response_text(self, result) -> str:
        """Build a concise text response for the A2A message."""
        lines = [
            f"**MedHarmony Analysis Complete** for {result.patient_name or result.patient_id}",
            "",
            f"📊 **{result.total_medications}** medications analyzed",
        ]

        if result.critical_issues > 0:
            lines.append(f"🔴 **{result.critical_issues}** critical issues found")
        if result.high_issues > 0:
            lines.append(f"🟠 **{result.high_issues}** high-priority issues")
        if result.moderate_issues > 0:
            lines.append(f"🟡 **{result.moderate_issues}** moderate issues")

        if result.tasks:
            lines.append("")
            lines.append(f"✅ **{len(result.tasks)}** follow-up tasks generated")

        if result.reasoning_trace:
            steps = result.reasoning_trace.get("step_count", 0)
            dur = result.reasoning_trace.get("total_duration_ms", 0)
            lines.append(f"🔍 Reasoning trace: {steps} steps in {dur:.0f} ms")

        lines.append("")
        lines.append(
            "See the attached **Clinician Safety Brief** (Artifact 1) and "
            "**Reasoning Trace** (Artifact 3) for full details."
        )

        return "\n".join(lines)

    async def get_task(self, task_id: str) -> dict | None:
        """Retrieve a task by ID."""
        return self.tasks.get(task_id)
