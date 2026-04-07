"""Clinical Guidelines MCP Server for MedHarmony.

Provides RAG (Retrieval-Augmented Generation) access to clinical
deprescribing guidelines including:
  - AGS Beers Criteria 2023
  - STOPP/START Criteria v3
  - General deprescribing protocols

Uses ChromaDB for vector storage and retrieval.
"""

from __future__ import annotations

import json
import asyncio
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


server = Server("medharmony-clinical-guidelines-mcp")

# =============================================================================
# Embedded Guidelines Knowledge Base
# (In production, this would be a ChromaDB vector store over full PDFs)
# =============================================================================

BEERS_CRITERIA = [
    {
        "id": "beers-benzo",
        "category": "Beers Criteria 2023",
        "drug_class": "Benzodiazepines",
        "drugs": ["diazepam", "lorazepam", "alprazolam", "clonazepam", "temazepam"],
        "recommendation": "Avoid in older adults (≥65 years)",
        "rationale": "Older adults have increased sensitivity to benzodiazepines and slower metabolism. Increased risk of cognitive impairment, delirium, falls, fractures, and motor vehicle crashes.",
        "severity": "high",
        "exceptions": "Seizure disorders, ethanol withdrawal, severe GAD where other therapies have failed",
        "deprescribing": "Taper by 10-25% every 1-2 weeks. Do NOT stop abruptly.",
    },
    {
        "id": "beers-anticholinergic",
        "category": "Beers Criteria 2023",
        "drug_class": "First-generation antihistamines (strongly anticholinergic)",
        "drugs": ["diphenhydramine", "hydroxyzine", "chlorpheniramine", "promethazine"],
        "recommendation": "Avoid in older adults",
        "rationale": "Highly anticholinergic; clearance reduced with advanced age. Risk of confusion, dry mouth, constipation, urinary retention. Tolerance develops when used as hypnotic.",
        "severity": "high",
        "exceptions": "Allergic reaction treatment (acute)",
        "deprescribing": "Can be stopped without tapering. Substitute with non-anticholinergic alternatives (cetirizine, loratadine).",
    },
    {
        "id": "beers-nsaids",
        "category": "Beers Criteria 2023",
        "drug_class": "Non-COX-selective NSAIDs",
        "drugs": ["ibuprofen", "naproxen", "diclofenac", "indomethacin", "piroxicam", "meloxicam"],
        "recommendation": "Avoid chronic use unless other alternatives not effective and patient can take a gastroprotective agent",
        "rationale": "Increases risk of GI bleeding/peptic ulcer disease especially in those >75 or taking anticoagulants/corticosteroids/antiplatelet agents. Also risk of fluid retention, AKI, and exacerbation of heart failure.",
        "severity": "high",
        "exceptions": "Short-term use (< 1 week) with gastroprotection",
        "deprescribing": "Switch to acetaminophen, topical NSAIDs, or non-pharmacologic approaches.",
        "interactions": "Especially dangerous with warfarin, apixaban, rivaroxaban (bleeding risk); with CKD (nephrotoxicity); with heart failure (fluid retention).",
    },
    {
        "id": "beers-ppi",
        "category": "Beers Criteria 2023",
        "drug_class": "Proton Pump Inhibitors",
        "drugs": ["omeprazole", "pantoprazole", "esomeprazole", "lansoprazole", "rabeprazole"],
        "recommendation": "Avoid scheduled use for >8 weeks unless for high-risk patients",
        "rationale": "Risk of C. difficile infection, bone loss, fractures, hypomagnesemia, vitamin B12 deficiency, and fundic gland polyps.",
        "severity": "moderate",
        "exceptions": "Barrett's esophagus, severe erosive esophagitis, pathological hypersecretory conditions",
        "deprescribing": "Step down to H2 blocker or taper to lowest effective dose. Try on-demand use.",
    },
    {
        "id": "beers-metformin-renal",
        "category": "Beers Criteria 2023 / FDA Guidance",
        "drug_class": "Biguanides",
        "drugs": ["metformin"],
        "recommendation": "Assess renal function. Contraindicated if eGFR <30. Reduce dose if eGFR 30-45.",
        "rationale": "Risk of lactic acidosis increases with declining renal function.",
        "severity": "high",
        "exceptions": "None for eGFR <30",
        "deprescribing": "If eGFR <30: discontinue. If eGFR 30-45: reduce to max 1000mg/day and monitor.",
    },
    {
        "id": "beers-duplicate-anticoagulant",
        "category": "Safety Alert",
        "drug_class": "Anticoagulants",
        "drugs": ["warfarin", "apixaban", "rivaroxaban", "edoxaban", "dabigatran"],
        "recommendation": "Never use two anticoagulants simultaneously unless during transition period",
        "rationale": "Extreme bleeding risk. If transitioning from warfarin to DOAC, must bridge appropriately with INR monitoring.",
        "severity": "critical",
        "exceptions": "Monitored bridging during transition under specialist guidance",
        "deprescribing": "When transitioning: stop warfarin, check INR, start DOAC when INR <2.0.",
    },
]

STOPP_START = [
    {
        "id": "stopp-nsaid-ckd",
        "category": "STOPP v3",
        "rule": "NSAID with eGFR <50 mL/min",
        "recommendation": "Stop NSAID — risk of further renal impairment",
        "severity": "high",
    },
    {
        "id": "stopp-nsaid-anticoag",
        "category": "STOPP v3",
        "rule": "NSAID with anticoagulant without PPI",
        "recommendation": "Stop NSAID or add PPI — high GI bleeding risk",
        "severity": "critical",
    },
    {
        "id": "stopp-benzo-fall",
        "category": "STOPP v3",
        "rule": "Benzodiazepine in patient with fall risk",
        "recommendation": "Taper and discontinue — increases fall and fracture risk",
        "severity": "high",
    },
    {
        "id": "start-anticoag-afib",
        "category": "START v3",
        "rule": "Anticoagulant for atrial fibrillation",
        "recommendation": "Ensure anticoagulant is prescribed for AF with CHA2DS2-VASc ≥2",
        "severity": "moderate",
    },
    {
        "id": "start-doac-over-warfarin",
        "category": "START v3",
        "rule": "DOAC preferred over warfarin for non-valvular AF",
        "recommendation": "Consider switching from warfarin to DOAC — lower bleeding risk, no INR monitoring needed",
        "severity": "moderate",
    },
]


def _search_guidelines(
    medications: list[str],
    age: int | None = None,
    conditions: list[str] | None = None,
    egfr: float | None = None,
) -> list[dict]:
    """Search guidelines relevant to the given medications and context."""
    results = []
    med_lower = [m.lower() for m in medications]
    cond_lower = [c.lower() for c in (conditions or [])]

    for entry in BEERS_CRITERIA:
        for drug in entry["drugs"]:
            if any(drug in m for m in med_lower):
                # Check age applicability
                if age and age >= 65:
                    results.append(entry)
                    break
                elif "renal" in entry.get("rationale", "").lower() and egfr and egfr < 45:
                    results.append(entry)
                    break

    for entry in STOPP_START:
        rule_lower = entry["rule"].lower()
        # Check if rule mentions any of the patient's medications
        if any(m in rule_lower for m in med_lower):
            results.append(entry)
        # Check if rule mentions CKD/renal and patient has low eGFR
        if egfr and egfr < 50 and ("egfr" in rule_lower or "renal" in rule_lower):
            if any(m in rule_lower for m in med_lower):
                if entry not in results:
                    results.append(entry)

    return results


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available clinical guideline tools."""
    return [
        Tool(
            name="search_deprescribing_guidelines",
            description=(
                "Search Beers Criteria 2023 and STOPP/START v3 for deprescribing "
                "recommendations applicable to a patient's medications, age, "
                "conditions, and renal function."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "medications": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of medication names",
                    },
                    "age": {
                        "type": "integer",
                        "description": "Patient age in years",
                    },
                    "conditions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of active conditions",
                    },
                    "egfr": {
                        "type": "number",
                        "description": "eGFR value (mL/min/1.73m2)",
                    },
                },
                "required": ["medications"],
            },
        ),
        Tool(
            name="get_beers_criteria",
            description="Get the full Beers Criteria 2023 knowledge base for a specific drug class.",
            inputSchema={
                "type": "object",
                "properties": {
                    "drug_class": {
                        "type": "string",
                        "description": "Drug class to look up (e.g., 'benzodiazepines', 'NSAIDs', 'PPIs')",
                    },
                },
                "required": ["drug_class"],
            },
        ),
        Tool(
            name="get_tapering_protocol",
            description="Get a deprescribing tapering protocol for a specific drug or drug class.",
            inputSchema={
                "type": "object",
                "properties": {
                    "drug_name": {
                        "type": "string",
                        "description": "Drug name or class",
                    },
                },
                "required": ["drug_name"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a clinical guideline tool."""
    try:
        if name == "search_deprescribing_guidelines":
            results = _search_guidelines(
                medications=arguments["medications"],
                age=arguments.get("age"),
                conditions=arguments.get("conditions"),
                egfr=arguments.get("egfr"),
            )
            return [TextContent(type="text", text=json.dumps(results, indent=2))]

        elif name == "get_beers_criteria":
            drug_class = arguments["drug_class"].lower()
            results = [
                e for e in BEERS_CRITERIA
                if drug_class in e.get("drug_class", "").lower()
                or drug_class in " ".join(e.get("drugs", []))
            ]
            return [TextContent(type="text", text=json.dumps(results, indent=2))]

        elif name == "get_tapering_protocol":
            drug = arguments["drug_name"].lower()
            results = [
                e for e in BEERS_CRITERIA
                if any(drug in d for d in e.get("drugs", []))
                and e.get("deprescribing")
            ]
            return [TextContent(type="text", text=json.dumps(results, indent=2))]

        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def main():
    """Run the Clinical Guidelines MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream)


if __name__ == "__main__":
    asyncio.run(main())
