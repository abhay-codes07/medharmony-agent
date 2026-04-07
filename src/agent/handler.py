"""A2A Task Handler for MedHarmony.

Processes incoming A2A tasks, extracts SHARP context,
routes to the reconciliation engine, and formats responses.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from loguru import logger

from src.core.reconciliation import ReconciliationEngine
from src.models.medication import SharpContext
from src.utils.sharp_context import extract_sharp_context, build_sharp_response_metadata


class TaskHandler:
    """Handles A2A tasks for the MedHarmony agent."""

    def __init__(self):
        self.engine = ReconciliationEngine()
        self.tasks: dict[str, dict] = {}  # In-memory task store

    async def handle_task(self, task_request: dict) -> dict:
        """Process an incoming A2A task request.

        A2A tasks follow the flow:
        1. Client sends tasks/send with a message
        2. Agent processes and returns result as an artifact
        """
        task_id = task_request.get("id", str(uuid.uuid4()))
        messages = task_request.get("messages", [])
        metadata = task_request.get("metadata", {})

        logger.info(f"Received task: {task_id}")

        # Extract SHARP context
        sharp_context = extract_sharp_context(metadata)

        # Also check for context in message parts
        if not sharp_context.patient_id and messages:
            for msg in messages:
                for part in msg.get("parts", []):
                    if part.get("type") == "data":
                        data = part.get("data", {})
                        if not sharp_context.patient_id:
                            sharp_ctx = extract_sharp_context(data)
                            if sharp_ctx.patient_id:
                                sharp_context = sharp_ctx

        # Extract user message text
        user_message = ""
        for msg in messages:
            if msg.get("role") == "user":
                for part in msg.get("parts", []):
                    if part.get("type") == "text":
                        user_message = part.get("text", "")

        # Check for patient_id in user message if not in SHARP context
        if not sharp_context.patient_id:
            # Try to extract patient ID from message text
            import re
            match = re.search(r'patient[_\s-]?(?:id)?[:\s]+(\S+)', user_message, re.I)
            if match:
                sharp_context.patient_id = match.group(1)

        # Determine which skill to invoke based on the message
        skill = self._determine_skill(user_message)
        logger.info(f"Invoking skill: {skill}")

        # Update task status
        self.tasks[task_id] = {
            "id": task_id,
            "status": "working",
            "messages": messages,
            "metadata": metadata,
        }

        try:
            # Run the analysis
            result = await self.engine.run_full_analysis(
                sharp_context=sharp_context,
                user_message=user_message,
            )

            # Build A2A response with artifacts
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
                    # Artifact 1: Clinician Brief (markdown)
                    {
                        "name": "clinician_safety_brief",
                        "description": "MedHarmony Clinician Safety Brief",
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
                        "description": "Structured medication analysis data",
                        "parts": [
                            {
                                "type": "data",
                                "data": result.model_dump(),
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
                    },
                },
            }

            self.tasks[task_id] = response_task
            logger.info(f"Task {task_id} completed successfully")
            return response_task

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            error_task = {
                "id": task_id,
                "status": "failed",
                "messages": messages + [
                    {
                        "role": "agent",
                        "parts": [
                            {
                                "type": "text",
                                "text": f"MedHarmony analysis failed: {str(e)}. "
                                        f"Please ensure a valid patient ID is provided "
                                        f"in the SHARP context.",
                            }
                        ],
                    }
                ],
                "metadata": metadata,
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
            # Default: run full analysis (includes all skills)
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

        lines.append("")
        lines.append("See the attached **Clinician Safety Brief** for full details.")

        return "\n".join(lines)

    async def get_task(self, task_id: str) -> dict | None:
        """Retrieve a task by ID."""
        return self.tasks.get(task_id)
