"""MCP Tool Bridge for MedHarmony.

Connects to all three MCP servers (FHIR, Drug Interactions, Clinical Guidelines)
via stdio and provides unified tool discovery and execution for the Gemini agent.
"""

from __future__ import annotations

import sys
from contextlib import AsyncExitStack
from typing import Any, Optional

from google.genai import types
from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


_TYPE_MAP: dict[str, types.Type] = {
    "string": types.Type.STRING,
    "integer": types.Type.INTEGER,
    "number": types.Type.NUMBER,
    "boolean": types.Type.BOOLEAN,
    "array": types.Type.ARRAY,
    "object": types.Type.OBJECT,
}

# Each entry: server_name → StdioServerParameters
_SERVERS: dict[str, StdioServerParameters] = {
    "fhir": StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp_servers.fhir_server.server"],
    ),
    "drug_interactions": StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp_servers.drug_interaction_server.server"],
    ),
    "clinical_guidelines": StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp_servers.clinical_guidelines_server.server"],
    ),
}


class MCPToolBridge:
    """Manages stdio connections to all MCP servers and bridges their tools to Gemini."""

    def __init__(self) -> None:
        self._exit_stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}
        self._tool_to_server: dict[str, str] = {}   # tool_name → server_name
        self._mcp_tools: dict[str, list] = {}        # server_name → [MCP Tool]

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def initialize(self) -> None:
        """Connect to all MCP servers and discover their tools."""
        await self._exit_stack.__aenter__()

        for server_name, params in _SERVERS.items():
            try:
                read, write = await self._exit_stack.enter_async_context(
                    stdio_client(params)
                )
                session: ClientSession = await self._exit_stack.enter_async_context(
                    ClientSession(read, write)
                )
                await session.initialize()

                tools_resp = await session.list_tools()
                tools = tools_resp.tools

                self._sessions[server_name] = session
                self._mcp_tools[server_name] = tools
                for tool in tools:
                    self._tool_to_server[tool.name] = server_name

                logger.info(
                    f"[mcp-bridge] Connected to '{server_name}': "
                    f"{len(tools)} tools {[t.name for t in tools]}"
                )

            except Exception as exc:
                logger.error(
                    f"[mcp-bridge] Failed to connect to '{server_name}': {exc}"
                )

    async def cleanup(self) -> None:
        """Disconnect from all MCP servers."""
        await self._exit_stack.__aexit__(None, None, None)
        logger.info("[mcp-bridge] All server connections closed")

    # -------------------------------------------------------------------------
    # Tool discovery
    # -------------------------------------------------------------------------

    def list_all_tools(self) -> dict[str, list]:
        """Return discovered MCP tools keyed by server name."""
        return dict(self._mcp_tools)

    def convert_mcp_tools_to_gemini_format(self) -> list[types.Tool]:
        """Convert all discovered MCP tool definitions into Gemini FunctionDeclarations.

        Returns:
            A list containing a single types.Tool with all function declarations,
            or an empty list if no tools are available.
        """
        declarations: list[types.FunctionDeclaration] = []

        for server_name, tools in self._mcp_tools.items():
            for tool in tools:
                try:
                    schema = tool.inputSchema
                    if not isinstance(schema, dict):
                        schema = {}

                    decl = types.FunctionDeclaration(
                        name=tool.name,
                        description=tool.description or "",
                        parameters=self._schema_to_gemini(schema),
                    )
                    declarations.append(decl)
                except Exception as exc:
                    logger.warning(
                        f"[mcp-bridge] Skipping tool '{tool.name}' from "
                        f"'{server_name}' (conversion error): {exc}"
                    )

        if not declarations:
            return []
        return [types.Tool(function_declarations=declarations)]

    def _schema_to_gemini(self, schema: dict) -> Optional[types.Schema]:
        """Recursively convert a JSON Schema dict to a Gemini types.Schema."""
        if not schema:
            return None

        raw_type = schema.get("type", "object")
        gemini_type = _TYPE_MAP.get(raw_type, types.Type.STRING)

        kwargs: dict[str, Any] = {"type": gemini_type}

        if desc := schema.get("description"):
            kwargs["description"] = desc

        if gemini_type == types.Type.OBJECT:
            raw_props = schema.get("properties", {})
            if raw_props:
                kwargs["properties"] = {
                    k: self._schema_to_gemini(v) for k, v in raw_props.items()
                }
            if req := schema.get("required"):
                kwargs["required"] = req

        elif gemini_type == types.Type.ARRAY:
            if items := schema.get("items"):
                kwargs["items"] = self._schema_to_gemini(items)

        if enum := schema.get("enum"):
            kwargs["enum"] = [str(e) for e in enum]

        return types.Schema(**kwargs)

    # -------------------------------------------------------------------------
    # Tool execution
    # -------------------------------------------------------------------------

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Route a tool call to the correct MCP server and return the text result.

        Args:
            tool_name: Name of the MCP tool to invoke.
            arguments: Tool arguments as a dict.

        Returns:
            Concatenated text content from all MCP response parts.

        Raises:
            ValueError: If the tool name is not registered.
            RuntimeError: If no active session exists for the tool's server.
        """
        server_name = self._tool_to_server.get(tool_name)
        if not server_name:
            raise ValueError(
                f"Unknown tool '{tool_name}'. "
                f"Available: {sorted(self._tool_to_server)}"
            )

        session = self._sessions.get(server_name)
        if not session:
            raise RuntimeError(
                f"No active session for server '{server_name}'"
            )

        logger.debug(f"[mcp-bridge] Routing '{tool_name}' → '{server_name}'")
        response = await session.call_tool(tool_name, arguments)

        text_parts = [
            content.text
            for content in response.content
            if hasattr(content, "text") and content.text
        ]
        return "\n".join(text_parts)

    # -------------------------------------------------------------------------
    # Async context manager interface
    # -------------------------------------------------------------------------

    async def __aenter__(self) -> "MCPToolBridge":
        await self.initialize()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.cleanup()
