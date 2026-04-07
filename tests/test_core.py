"""Tests for MedHarmony Agent."""

import os
import types as pytypes
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.models.medication import (
    Medication,
    MedicationList,
    PatientContext,
    Allergy,
    Condition,
    LabResult,
    SharpContext,
    MedHarmonyResult,
    Severity,
)
from src.utils.sharp_context import extract_sharp_context, build_sharp_response_metadata
from src.agent.agent_card import get_agent_card


# =============================================================================
# Model Tests
# =============================================================================

class TestModels:
    def test_medication_creation(self):
        med = Medication(name="Metformin", dose="500 mg", frequency="twice daily")
        assert med.name == "Metformin"
        assert med.status == "active"

    def test_patient_context(self):
        ctx = PatientContext(
            patient_id="test-001",
            name="Test Patient",
            age=75,
            sex="male",
        )
        assert ctx.patient_id == "test-001"
        assert ctx.allergies == []
        assert ctx.medication_lists == []

    def test_medication_list(self):
        ml = MedicationList(
            source="admission",
            medications=[
                Medication(name="Aspirin", dose="81 mg"),
                Medication(name="Lisinopril", dose="10 mg"),
            ],
        )
        assert len(ml.medications) == 2

    def test_result_model(self):
        result = MedHarmonyResult(
            patient_id="test-001",
            total_medications=5,
            critical_issues=1,
            high_issues=2,
            moderate_issues=1,
        )
        assert result.critical_issues == 1
        assert result.clinician_brief == ""


# =============================================================================
# SHARP Context Tests
# =============================================================================

class TestSharpContext:
    def test_extract_from_sharp_key(self):
        metadata = {
            "sharp": {
                "patient_id": "patient-123",
                "fhir_server_url": "https://fhir.example.com/R4",
                "fhir_access_token": "token-abc",
            }
        }
        ctx = extract_sharp_context(metadata)
        assert ctx.patient_id == "patient-123"
        assert ctx.fhir_server_url == "https://fhir.example.com/R4"
        assert ctx.fhir_access_token == "token-abc"

    def test_extract_from_flat_keys(self):
        metadata = {
            "patient_id": "patient-456",
            "fhir_server_url": "https://fhir2.example.com/R4",
        }
        ctx = extract_sharp_context(metadata)
        assert ctx.patient_id == "patient-456"

    def test_extract_from_fhir_context(self):
        metadata = {
            "fhirContext": [
                {"reference": "Patient/patient-789"},
                {"reference": "Encounter/enc-001"},
            ]
        }
        ctx = extract_sharp_context(metadata)
        assert ctx.patient_id == "patient-789"
        assert ctx.encounter_id == "enc-001"

    def test_extract_empty_metadata(self):
        ctx = extract_sharp_context({})
        assert ctx.patient_id is None

    def test_build_response_metadata(self):
        ctx = SharpContext(
            patient_id="p-001",
            fhir_server_url="https://fhir.example.com",
            encounter_id="enc-001",
        )
        meta = build_sharp_response_metadata(ctx)
        assert meta["sharp"]["patient_id"] == "p-001"


# =============================================================================
# Agent Card Tests
# =============================================================================

class TestAgentCard:
    def test_agent_card_structure(self):
        card = get_agent_card()
        assert card["name"] == "MedHarmony"
        assert "skills" in card
        assert len(card["skills"]) == 4

    def test_agent_card_skills(self):
        card = get_agent_card()
        skill_ids = [s["id"] for s in card["skills"]]
        assert "medication-reconciliation" in skill_ids
        assert "drug-interaction-analysis" in skill_ids
        assert "deprescribing-advisor" in skill_ids
        assert "clinician-safety-brief" in skill_ids

    def test_agent_card_sharp_extension(self):
        card = get_agent_card()
        sharp = card["extensions"]["sharp"]
        assert sharp["supportsPatientContext"] is True
        assert "MedicationRequest" in sharp["requiredFhirResources"]
        assert sharp["fhirVersion"] == "R4"


# =============================================================================
# Demo Patient Tests
# =============================================================================

class TestDemoPatient:
    @patch("src.core.reconciliation.LLMClient")
    def test_demo_patient_has_dangerous_combos(self, _mock_llm):
        """The demo patient should have intentionally dangerous medication combos
        that MedHarmony should catch."""
        from src.core.reconciliation import ReconciliationEngine
        engine = ReconciliationEngine()
        patient = engine._get_demo_patient_context("demo-001")

        assert patient.name == "Margaret Thompson"
        assert patient.age == 78

        # Should have CKD (eGFR 32)
        egfr = next((l for l in patient.lab_results if l.name == "eGFR"), None)
        assert egfr is not None
        assert egfr.value == 32.0

        # Should be on ibuprofen (NSAID) — dangerous with CKD + warfarin
        all_meds = []
        for ml in patient.medication_lists:
            all_meds.extend([m.name.lower() for m in ml.medications])
        assert any("ibuprofen" in m for m in all_meds)

        # Should be on warfarin + potentially apixaban (dual anticoagulant risk)
        assert any("warfarin" in m for m in all_meds)

        # Should be on diazepam (Beers Criteria for elderly)
        assert any("diazepam" in m for m in all_meds)

        # Should be on diphenhydramine (Beers Criteria — anticholinergic)
        assert any("diphenhydramine" in m for m in all_meds)

        # Should have high potassium
        potassium = next((l for l in patient.lab_results if l.name == "Potassium"), None)
        assert potassium is not None
        assert potassium.value > 5.0

    @patch("src.core.reconciliation.LLMClient")
    def test_demo_has_reconciliation_discrepancies(self, _mock_llm):
        """Demo patient should have differences between admission and discharge lists."""
        from src.core.reconciliation import ReconciliationEngine
        engine = ReconciliationEngine()
        patient = engine._get_demo_patient_context("demo-001")

        admission_meds = set()
        discharge_meds = set()
        for ml in patient.medication_lists:
            for m in ml.medications:
                if ml.source == "admission_home_meds":
                    admission_meds.add(m.name.lower())
                elif ml.source == "discharge_medications":
                    discharge_meds.add(m.name.lower())

        # There should be meds in admission not in discharge (and vice versa)
        only_admission = admission_meds - discharge_meds
        only_discharge = discharge_meds - admission_meds
        assert len(only_admission) > 0, "Should have meds dropped at discharge"
        assert len(only_discharge) > 0, "Should have new meds at discharge"


# =============================================================================
# MCP Tool Bridge Tests
# =============================================================================

@pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="Requires GEMINI_API_KEY to indicate live integration environment",
)
@pytest.mark.asyncio
class TestMCPToolBridgeListsTools:
    """Integration test: MCPToolBridge connects to MCP servers and discovers tools."""

    async def test_mcp_tool_bridge_lists_tools(self):
        from src.core.mcp_tool_bridge import MCPToolBridge

        async with MCPToolBridge() as bridge:
            tools_by_server = bridge.list_all_tools()

            # All three servers should be connected
            assert "fhir" in tools_by_server, "FHIR server should be connected"
            assert "drug_interactions" in tools_by_server, "Drug server should be connected"
            assert "clinical_guidelines" in tools_by_server, "Guidelines server should be connected"

            # Each server should expose at least one tool
            assert len(tools_by_server["fhir"]) >= 1
            assert len(tools_by_server["drug_interactions"]) >= 1
            assert len(tools_by_server["clinical_guidelines"]) >= 1

            # FHIR server should have get_patient_summary
            fhir_names = {t.name for t in tools_by_server["fhir"]}
            assert "get_patient_summary" in fhir_names

            # Drug server should have check_drug_interactions
            drug_names = {t.name for t in tools_by_server["drug_interactions"]}
            assert "check_drug_interactions" in drug_names

            # Guidelines server should have search_deprescribing_guidelines
            guide_names = {t.name for t in tools_by_server["clinical_guidelines"]}
            assert "search_deprescribing_guidelines" in guide_names


# =============================================================================
# Gemini Tool Format Conversion Tests
# =============================================================================

@pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="Requires GEMINI_API_KEY to indicate live integration environment",
)
class TestGeminiToolFormatConversion:
    """Tests that MCP tool definitions are correctly converted to Gemini format."""

    def _make_mock_tool(self, name: str, description: str, schema: dict):
        """Create a minimal mock MCP Tool object."""
        tool = MagicMock()
        tool.name = name
        tool.description = description
        tool.inputSchema = schema
        return tool

    def test_schema_string_type(self):
        from src.core.mcp_tool_bridge import MCPToolBridge
        from google.genai import types

        bridge = MCPToolBridge()
        schema = bridge._schema_to_gemini({"type": "string", "description": "A drug name"})
        assert schema is not None
        assert schema.type == types.Type.STRING
        assert schema.description == "A drug name"

    def test_schema_object_with_properties(self):
        from src.core.mcp_tool_bridge import MCPToolBridge
        from google.genai import types

        bridge = MCPToolBridge()
        schema = bridge._schema_to_gemini({
            "type": "object",
            "properties": {
                "patient_id": {"type": "string", "description": "Patient ID"},
                "age": {"type": "integer", "description": "Age in years"},
            },
            "required": ["patient_id"],
        })
        assert schema is not None
        assert schema.type == types.Type.OBJECT
        assert "patient_id" in schema.properties
        assert "age" in schema.properties
        assert schema.properties["patient_id"].type == types.Type.STRING
        assert schema.properties["age"].type == types.Type.INTEGER
        assert schema.required == ["patient_id"]

    def test_schema_array_with_items(self):
        from src.core.mcp_tool_bridge import MCPToolBridge
        from google.genai import types

        bridge = MCPToolBridge()
        schema = bridge._schema_to_gemini({
            "type": "array",
            "items": {"type": "string"},
            "description": "List of drug names",
        })
        assert schema is not None
        assert schema.type == types.Type.ARRAY
        assert schema.items is not None
        assert schema.items.type == types.Type.STRING

    def test_gemini_tool_format_conversion(self):
        """Full conversion: mock MCP tools → Gemini Tool object."""
        from src.core.mcp_tool_bridge import MCPToolBridge
        from google.genai import types

        bridge = MCPToolBridge()

        # Inject mock tools directly (bypasses live server connection)
        bridge._mcp_tools = {
            "drug_interactions": [
                self._make_mock_tool(
                    "check_drug_interactions",
                    "Check drug-drug interactions",
                    {
                        "type": "object",
                        "properties": {
                            "drug_list": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of drug names",
                            }
                        },
                        "required": ["drug_list"],
                    },
                )
            ],
            "clinical_guidelines": [
                self._make_mock_tool(
                    "search_deprescribing_guidelines",
                    "Search Beers Criteria and STOPP/START",
                    {
                        "type": "object",
                        "properties": {
                            "medications": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "age": {"type": "integer"},
                            "egfr": {"type": "number"},
                        },
                        "required": ["medications"],
                    },
                )
            ],
        }
        bridge._tool_to_server = {
            "check_drug_interactions": "drug_interactions",
            "search_deprescribing_guidelines": "clinical_guidelines",
        }

        gemini_tools = bridge.convert_mcp_tools_to_gemini_format()

        assert len(gemini_tools) == 1, "Should return a single Tool object"
        tool_obj = gemini_tools[0]
        assert isinstance(tool_obj, types.Tool)

        decl_names = {d.name for d in tool_obj.function_declarations}
        assert "check_drug_interactions" in decl_names
        assert "search_deprescribing_guidelines" in decl_names

        # Verify parameter schema is correct
        check_decl = next(
            d for d in tool_obj.function_declarations
            if d.name == "check_drug_interactions"
        )
        assert check_decl.parameters is not None
        assert check_decl.parameters.type == types.Type.OBJECT
        assert "drug_list" in check_decl.parameters.properties
        assert check_decl.parameters.properties["drug_list"].type == types.Type.ARRAY
