"""MedHarmony Reasoning Tracer — observability for the agent loop.

Records every step: LLM calls, tool calls, tool results, pipeline steps, and errors.
Provides to_markdown() for clinician-readable timelines and to_json() for programmatic access.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional


StepType = Literal["llm_call", "tool_call", "tool_result", "pipeline_step", "error"]


@dataclass
class TraceEntry:
    timestamp: str
    step_type: StepType
    tool_name: Optional[str]
    arguments: Optional[dict]
    result_summary: Optional[str]
    duration_ms: Optional[float]
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "step_type": self.step_type,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "result_summary": self.result_summary,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


class ReasoningTracer:
    """Records every step of the MedHarmony agent loop for full observability.

    Usage::

        tracer = ReasoningTracer()

        # Record a named pipeline step
        start = tracer.start_timer()
        try:
            result = await do_step()
            tracer.record("pipeline_step", tool_name="reconciliation",
                          result_summary="completed", duration_ms=tracer.elapsed(start))
        except Exception as e:
            tracer.record("error", tool_name="reconciliation",
                          error=str(e), duration_ms=tracer.elapsed(start))

        # Record a tool call
        tracer.record("tool_call", tool_name="check_drug_interactions",
                      arguments={"drugs": ["warfarin", "ibuprofen"]})

        # Record a tool result
        tracer.record("tool_result", tool_name="check_drug_interactions",
                      result_summary="Found 2 interactions", duration_ms=142.3)

        print(tracer.to_markdown())
    """

    def __init__(self) -> None:
        self.entries: list[TraceEntry] = []
        self._wall_start = time.monotonic()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        step_type: StepType,
        *,
        tool_name: Optional[str] = None,
        arguments: Optional[dict] = None,
        result_summary: Optional[str] = None,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """Append a single trace entry."""
        self.entries.append(
            TraceEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                step_type=step_type,
                tool_name=tool_name,
                arguments=arguments,
                result_summary=result_summary,
                duration_ms=duration_ms,
                error=error,
            )
        )

    # ------------------------------------------------------------------
    # Timer helpers
    # ------------------------------------------------------------------

    @staticmethod
    def start_timer() -> float:
        """Return a monotonic start timestamp for duration measurement."""
        return time.monotonic()

    @staticmethod
    def elapsed(start: float) -> float:
        """Return elapsed milliseconds since *start*."""
        return round((time.monotonic() - start) * 1000, 1)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        """Return the full trace as a JSON-serialisable dict."""
        return {
            "total_duration_ms": round((time.monotonic() - self._wall_start) * 1000, 1),
            "step_count": len(self.entries),
            "entries": [e.to_dict() for e in self.entries],
        }

    def to_markdown(self) -> str:
        """Render the trace as a clinician-readable Markdown timeline table."""
        total_ms = round((time.monotonic() - self._wall_start) * 1000, 1)

        lines = [
            "## MedHarmony Reasoning Trace",
            "",
            f"**Steps recorded:** {len(self.entries)}  ",
            f"**Total wall time:** {total_ms} ms",
            "",
            "| # | Time (UTC) | Type | Tool / Step | Summary | Duration |",
            "|---|-----------|------|-------------|---------|----------|",
        ]

        for i, e in enumerate(self.entries, 1):
            ts = e.timestamp[11:19]  # HH:MM:SS
            step_type = e.step_type.replace("_", " ").title()
            tool = f"`{e.tool_name}`" if e.tool_name else "—"

            if e.error:
                summary = f"❌ {e.error[:80]}"
            elif e.result_summary:
                summary = e.result_summary[:80]
            else:
                summary = "—"

            dur = f"{e.duration_ms:.0f} ms" if e.duration_ms is not None else "—"
            lines.append(f"| {i} | {ts} | {step_type} | {tool} | {summary} | {dur} |")

        return "\n".join(lines)
