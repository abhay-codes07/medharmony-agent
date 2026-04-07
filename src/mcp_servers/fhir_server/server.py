"""FHIR MCP Server for MedHarmony.

Exposes FHIR patient data as MCP tools that the A2A agent can invoke.
Tools:
  - get_patient_demographics
  - get_medications
  - get_allergies
  - get_conditions
  - get_lab_results
  - get_patient_summary
"""

from __future__ import annotations

import json
import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from src.utils.fhir_client import FHIRClient


# Create MCP server
server = Server("medharmony-fhir-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available FHIR tools."""
    return [
        Tool(
            name="get_patient_demographics",
            description=(
                "Get patient demographics including name, age, sex, and weight. "
                "Requires a FHIR patient ID."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "FHIR Patient resource ID",
                    },
                    "fhir_server_url": {
                        "type": "string",
                        "description": "FHIR server base URL (optional)",
                    },
                },
                "required": ["patient_id"],
            },
        ),
        Tool(
            name="get_medications",
            description=(
                "Get all active medications for a patient from MedicationRequest "
                "and MedicationStatement resources. Returns drug names, doses, "
                "frequencies, and RxNorm codes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "FHIR Patient resource ID",
                    },
                    "fhir_server_url": {
                        "type": "string",
                        "description": "FHIR server base URL (optional)",
                    },
                },
                "required": ["patient_id"],
            },
        ),
        Tool(
            name="get_allergies",
            description=(
                "Get patient allergy records from AllergyIntolerance resources. "
                "Returns substances, reactions, and severity."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "FHIR Patient resource ID",
                    },
                    "fhir_server_url": {
                        "type": "string",
                        "description": "FHIR server base URL (optional)",
                    },
                },
                "required": ["patient_id"],
            },
        ),
        Tool(
            name="get_conditions",
            description=(
                "Get active conditions/diagnoses for a patient from Condition resources. "
                "Returns condition names, ICD-10 codes, and status."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "FHIR Patient resource ID",
                    },
                    "fhir_server_url": {
                        "type": "string",
                        "description": "FHIR server base URL (optional)",
                    },
                },
                "required": ["patient_id"],
            },
        ),
        Tool(
            name="get_lab_results",
            description=(
                "Get recent key lab results for a patient. Includes renal function "
                "(creatinine, eGFR), hepatic function (ALT, AST), HbA1c, electrolytes, "
                "CBC, and INR. Flags abnormal values."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "FHIR Patient resource ID",
                    },
                    "fhir_server_url": {
                        "type": "string",
                        "description": "FHIR server base URL (optional)",
                    },
                },
                "required": ["patient_id"],
            },
        ),
        Tool(
            name="get_patient_summary",
            description=(
                "Get a complete patient context summary including demographics, "
                "all medications, allergies, conditions, and key lab results. "
                "This is the primary tool for medication reconciliation."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "FHIR Patient resource ID",
                    },
                    "fhir_server_url": {
                        "type": "string",
                        "description": "FHIR server base URL (optional)",
                    },
                },
                "required": ["patient_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a FHIR tool."""
    patient_id = arguments.get("patient_id")
    fhir_url = arguments.get("fhir_server_url", "https://hapi.fhir.org/baseR4")

    client = FHIRClient(base_url=fhir_url)

    try:
        if name == "get_patient_demographics":
            patient = await client.get_patient(patient_id)
            result = {
                "name": client._extract_name(patient),
                "age": client._calculate_age(patient),
                "sex": patient.get("gender"),
                "birth_date": patient.get("birthDate"),
            }

        elif name == "get_medications":
            med_lists = await client._get_medication_lists(patient_id)
            result = [ml.model_dump() for ml in med_lists]

        elif name == "get_allergies":
            allergies = await client._get_allergies(patient_id)
            result = [a.model_dump() for a in allergies]

        elif name == "get_conditions":
            conditions = await client._get_conditions(patient_id)
            result = [c.model_dump() for c in conditions]

        elif name == "get_lab_results":
            labs = await client._get_lab_results(patient_id)
            result = [l.model_dump() for l in labs]

        elif name == "get_patient_summary":
            ctx = await client.get_patient_context(patient_id)
            result = ctx.model_dump()

        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e), "tool": name, "patient_id": patient_id}),
        )]


async def main():
    """Run the FHIR MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream)


if __name__ == "__main__":
    asyncio.run(main())
