"""Centralized agentic reasoning loop for MedHarmony.

Wraps LLMClient.analyze_with_tools with structured loguru tracing and optional
ReasoningTracer integration so that every tool call, argument set, and result
is captured for observability.
"""

from __future__ import annotations

import time
from typing import Optional

from google.genai import types
from loguru import logger

from src.core.llm_client import LLMClient
from src.core.mcp_tool_bridge import MCPToolBridge
from src.utils.observability import ReasoningTracer


class AgentLoop:
    """Orchestrates Gemini reasoning + MCP tool calls with full execution tracing."""

    def __init__(
        self,
        llm: LLMClient,
        bridge: MCPToolBridge,
        tracer: Optional[ReasoningTracer] = None,
    ) -> None:
        self.llm = llm
        self.bridge = bridge
        self.tracer = tracer

    async def run(
        self,
        prompt: str,
        context: Optional[str] = None,
        tool_filter: Optional[list[str]] = None,
    ) -> str:
        """Run one agentic reasoning cycle.

        Gemini autonomously decides which tools to call from the filtered set,
        executes them via the MCPToolBridge, and loops until it produces a final
        text response (or the max-iteration cap in LLMClient is reached).

        Every tool call and result is logged at INFO level and recorded in the
        optional ReasoningTracer for downstream observability.

        Args:
            prompt: Clinical reasoning prompt for Gemini.
            context: Optional prior conversation context (e.g. patient summary).
            tool_filter: If provided, only these tool names are exposed to Gemini.
                         Pass None to expose all tools from all connected servers.

        Returns:
            Final text response from Gemini after all tool calls complete.
        """
        gemini_tools = self.bridge.convert_mcp_tools_to_gemini_format()

        # Apply optional tool filter
        if tool_filter is not None:
            filter_set = set(tool_filter)
            filtered_decls: list[types.FunctionDeclaration] = []
            for tool_obj in gemini_tools:
                for decl in tool_obj.function_declarations or []:
                    if decl.name in filter_set:
                        filtered_decls.append(decl)
            gemini_tools = (
                [types.Tool(function_declarations=filtered_decls)]
                if filtered_decls
                else []
            )

        available_names = [
            d.name
            for t in gemini_tools
            for d in (t.function_declarations or [])
        ]
        logger.info(
            f"[agent-loop] Starting — {len(available_names)} tools available: "
            f"{available_names}"
        )

        # Record the LLM call start in the tracer
        if self.tracer:
            self.tracer.record(
                "llm_call",
                tool_name="gemini",
                arguments={"tools": available_names, "prompt_length": len(prompt)},
                result_summary="starting agentic loop",
            )

        async def _traced_executor(tool_name: str, arguments: dict) -> str:
            logger.info(f"  → calling tool: {tool_name}({arguments})")

            # Record tool call
            if self.tracer:
                self.tracer.record(
                    "tool_call",
                    tool_name=tool_name,
                    arguments=arguments,
                )

            call_start = time.monotonic()
            try:
                result = await self.bridge.execute_tool(tool_name, arguments)
                dur = ReasoningTracer.elapsed(call_start)
                logger.info(f"  ✓ {tool_name} returned {len(result)} chars")

                # Record tool result
                if self.tracer:
                    self.tracer.record(
                        "tool_result",
                        tool_name=tool_name,
                        result_summary=result[:200] if result else "(empty)",
                        duration_ms=dur,
                    )
                return result

            except Exception as exc:
                dur = ReasoningTracer.elapsed(call_start)
                logger.warning(f"  ✗ {tool_name} failed: {exc}")

                if self.tracer:
                    self.tracer.record(
                        "error",
                        tool_name=tool_name,
                        error=str(exc),
                        duration_ms=dur,
                    )
                raise

        llm_start = time.monotonic()
        response = await self.llm.analyze_with_tools(
            prompt=prompt,
            tools=gemini_tools,
            tool_executor=_traced_executor,
            context=context,
        )

        llm_dur = ReasoningTracer.elapsed(llm_start)
        logger.info(
            f"[agent-loop] Complete — response length: {len(response)} chars"
        )

        if self.tracer:
            self.tracer.record(
                "llm_call",
                tool_name="gemini",
                result_summary=f"agentic loop complete ({len(response)} chars)",
                duration_ms=llm_dur,
            )

        return response
