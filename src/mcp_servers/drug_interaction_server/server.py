"""Drug Interaction MCP Server for MedHarmony.

Exposes drug interaction checking as MCP tools using RxNorm and OpenFDA APIs.
Tools:
  - check_drug_interactions
  - get_drug_info
  - check_renal_dosing
"""

from __future__ import annotations

import json
import asyncio
from typing import Optional

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from src.agent.config import RXNORM_API_URL


server = Server("medharmony-drug-interaction-mcp")

RXNORM_BASE = RXNORM_API_URL


async def _rxnorm_get(path: str, params: Optional[dict] = None) -> dict:
    """Make a GET request to the RxNorm API."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{RXNORM_BASE}/{path}",
            params=params,
            headers={"Accept": "application/json"},
        )
        if response.status_code == 200:
            return response.json()
        return {}


async def _openfda_get(rxcui: str) -> dict:
    """Query OpenFDA for drug label information."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            "https://api.fda.gov/drug/label.json",
            params={"search": f'openfda.rxcui:"{rxcui}"', "limit": "1"},
        )
        if response.status_code == 200:
            return response.json()
        return {}


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available drug interaction tools."""
    return [
        Tool(
            name="check_drug_interactions",
            description=(
                "Check for known drug-drug interactions between two or more "
                "medications using RxNorm interaction API. Provide drug names "
                "or RxNorm CUI codes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "drug_list": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of drug names or RxNorm CUI codes",
                    },
                },
                "required": ["drug_list"],
            },
        ),
        Tool(
            name="get_drug_info",
            description=(
                "Get detailed drug information including warnings, "
                "contraindications, and adverse reactions from drug labels."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "drug_name": {
                        "type": "string",
                        "description": "Drug name or RxNorm CUI code",
                    },
                },
                "required": ["drug_name"],
            },
        ),
        Tool(
            name="lookup_rxnorm",
            description=(
                "Look up the RxNorm CUI code for a drug name. Useful for "
                "normalizing drug names across different sources."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "drug_name": {
                        "type": "string",
                        "description": "Drug name to look up",
                    },
                },
                "required": ["drug_name"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a drug interaction tool."""
    try:
        if name == "check_drug_interactions":
            result = await _check_interactions(arguments["drug_list"])
        elif name == "get_drug_info":
            result = await _get_drug_info(arguments["drug_name"])
        elif name == "lookup_rxnorm":
            result = await _lookup_rxnorm(arguments["drug_name"])
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e), "tool": name}),
        )]


async def _lookup_rxnorm(drug_name: str) -> dict:
    """Look up RxNorm CUI for a drug name."""
    data = await _rxnorm_get("rxcui.json", {"name": drug_name, "search": "1"})
    id_group = data.get("idGroup", {})
    rxnorm_ids = id_group.get("rxnormId", [])

    if rxnorm_ids:
        return {"drug_name": drug_name, "rxcui": rxnorm_ids[0]}

    # Try approximate match
    data = await _rxnorm_get("approximateTerm.json", {"term": drug_name, "maxEntries": "3"})
    candidates = data.get("approximateGroup", {}).get("candidate", [])
    if candidates:
        return {
            "drug_name": drug_name,
            "rxcui": candidates[0].get("rxcui"),
            "match_name": candidates[0].get("name", ""),
            "score": candidates[0].get("score", ""),
        }

    return {"drug_name": drug_name, "rxcui": None, "error": "Not found"}


async def _check_interactions(drug_list: list[str]) -> dict:
    """Check interactions between a list of drugs."""
    # First, resolve all drug names to RxNorm CUIs
    rxcuis = []
    resolved = []
    for drug in drug_list:
        if drug.isdigit():
            rxcuis.append(drug)
            resolved.append({"name": drug, "rxcui": drug})
        else:
            info = await _lookup_rxnorm(drug)
            if info.get("rxcui"):
                rxcuis.append(info["rxcui"])
                resolved.append({"name": drug, "rxcui": info["rxcui"]})

    if len(rxcuis) < 2:
        return {
            "interactions": [],
            "message": "Need at least 2 resolved drug CUIs to check interactions",
            "resolved_drugs": resolved,
        }

    # Query RxNorm interaction API
    rxcui_str = "+".join(rxcuis)
    data = await _rxnorm_get(f"interaction/list.json", {"rxcuis": rxcui_str})

    interactions = []
    interaction_groups = data.get("fullInteractionTypeGroup", [])
    for group in interaction_groups:
        source = group.get("sourceName", "Unknown")
        for itype in group.get("fullInteractionType", []):
            for pair in itype.get("interactionPair", []):
                interactions.append({
                    "source": source,
                    "severity": pair.get("severity", "N/A"),
                    "description": pair.get("description", ""),
                    "drugs": [
                        concept.get("minConceptItem", {}).get("name", "")
                        for concept in pair.get("interactionConcept", [])
                    ],
                })

    return {
        "resolved_drugs": resolved,
        "interaction_count": len(interactions),
        "interactions": interactions,
    }


async def _get_drug_info(drug_name: str) -> dict:
    """Get drug label information from OpenFDA."""
    # Resolve to RxCUI first
    rxinfo = await _lookup_rxnorm(drug_name)
    rxcui = rxinfo.get("rxcui")

    result = {"drug_name": drug_name, "rxcui": rxcui}

    if rxcui:
        fda_data = await _openfda_get(rxcui)
        results = fda_data.get("results", [])
        if results:
            label = results[0]
            result["warnings"] = label.get("warnings", ["N/A"])[:2]
            result["contraindications"] = label.get("contraindications", ["N/A"])[:2]
            result["drug_interactions"] = label.get("drug_interactions", ["N/A"])[:2]
            result["adverse_reactions"] = label.get("adverse_reactions", ["N/A"])[:1]
            result["dosage_and_administration"] = label.get("dosage_and_administration", ["N/A"])[:1]

    return result


async def main():
    """Run the Drug Interaction MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream)


if __name__ == "__main__":
    asyncio.run(main())
