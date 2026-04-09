"""Integration tests against the public HAPI FHIR test server.

These tests make real network calls and depend on hapi.fhir.org being available.
Run with:
    pytest tests/test_real_fhir.py -v -m integration

Skip them in CI:
    pytest tests/ -v --ignore=tests/test_real_fhir.py

Or toggle with:
    pytest tests/ -v -m "not integration"
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Mark every test in this file as an integration test
pytestmark = pytest.mark.integration

HAPI_URL = "https://hapi.fhir.org/baseR4"
SAMPLE_IDS_PATH = (
    Path(__file__).parent.parent / "data" / "synthetic_patients" / "sample_patient_ids.json"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def demo_sharp_context():
    """SHARP context pointing at the built-in offline demo patient."""
    from src.models.medication import SharpContext

    return SharpContext(
        patient_id="demo-001",
        fhir_server_url=HAPI_URL,
        user_role="pharmacist",
    )


@pytest.fixture
def hapi_sharp_context():
    """SHARP context pointing at a known-good HAPI FHIR patient.

    Uses the first non-demo patient from sample_patient_ids.json.
    Skips if no live patients are configured.
    """
    from src.models.medication import SharpContext

    if not SAMPLE_IDS_PATH.exists():
        pytest.skip("sample_patient_ids.json not found — run seed_demo_data.py first")

    records = json.loads(SAMPLE_IDS_PATH.read_text())
    live_records = [r for r in records if r.get("fhir_server") != "local-demo"]

    if not live_records:
        pytest.skip("No live HAPI patient IDs in sample_patient_ids.json")

    record = live_records[0]
    return SharpContext(
        patient_id=record["patient_id"],
        fhir_server_url=record.get("fhir_server", HAPI_URL),
        user_role="pharmacist",
    )


# ---------------------------------------------------------------------------
# Tests: FHIRClient
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fhir_client_loads_demo_patient_fallback(demo_sharp_context):
    """Full analysis should fall back to demo patient when patient_id is demo-001."""
    from src.core.reconciliation import ReconciliationEngine

    engine = ReconciliationEngine()
    result = await engine.run_full_analysis(demo_sharp_context)

    assert result.patient_id is not None
    assert result.total_medications > 0
    assert isinstance(result.reconciliation, list)
    assert isinstance(result.interactions, list)
    assert isinstance(result.deprescribing, list)
    assert result.clinician_brief, "Expected non-empty clinician brief"


@pytest.mark.asyncio
async def test_fhir_client_handles_missing_patient_gracefully():
    """Agent should not crash when patient_id is not found on the FHIR server."""
    from src.models.medication import SharpContext
    from src.utils.fhir_client import FHIRClient

    client = FHIRClient(base_url=HAPI_URL)
    # Use a clearly non-existent ID
    ctx = await client.get_patient_context("this-patient-does-not-exist-9999999")
    # Should return a minimal PatientContext rather than raising
    assert ctx is not None
    assert ctx.patient_id == "this-patient-does-not-exist-9999999"


@pytest.mark.asyncio
async def test_fhir_client_handles_timeout_gracefully():
    """FHIRClient should raise an exception (not hang) on timeout."""
    from src.utils.fhir_client import FHIRClient

    # Use a very low timeout to force a timeout error
    client = FHIRClient(base_url="https://httpbin.org/delay/30", timeout=1)
    with pytest.raises(Exception):
        await client.get_patient_context("any-id")


@pytest.mark.asyncio
async def test_full_analysis_result_structure(demo_sharp_context):
    """Result must have all required fields in correct types."""
    from src.core.reconciliation import ReconciliationEngine
    from src.models.medication import MedHarmonyResult

    engine = ReconciliationEngine()
    result = await engine.run_full_analysis(demo_sharp_context)

    assert isinstance(result, MedHarmonyResult)
    assert isinstance(result.critical_issues, int)
    assert isinstance(result.high_issues, int)
    assert isinstance(result.moderate_issues, int)
    assert isinstance(result.tasks, list)
    assert isinstance(result.reasoning_trace, dict), "reasoning_trace should be a dict"
    assert "entries" in result.reasoning_trace
    assert "total_duration_ms" in result.reasoning_trace


@pytest.mark.asyncio
async def test_analysis_safety_guards_applied(demo_sharp_context):
    """Every critical interaction should have a non-empty recommendation and evidence source."""
    from src.core.reconciliation import ReconciliationEngine
    from src.models.medication import Severity

    engine = ReconciliationEngine()
    result = await engine.run_full_analysis(demo_sharp_context)

    for ix in result.interactions:
        if ix.severity == Severity.CRITICAL:
            assert ix.recommendation.strip(), (
                f"Critical interaction {ix.drug_a} has no recommendation"
            )
            assert ix.evidence_source, (
                f"Critical interaction {ix.drug_a} has no evidence source"
            )


@pytest.mark.asyncio
async def test_live_hapi_patient(hapi_sharp_context):
    """Run full analysis against a live patient on the public HAPI server."""
    from src.core.reconciliation import ReconciliationEngine

    engine = ReconciliationEngine()
    result = await engine.run_full_analysis(hapi_sharp_context)

    # Basic structural checks — we can't predict what the live patient has
    assert result.patient_id == hapi_sharp_context.patient_id
    assert result.clinician_brief, "Expected non-empty clinician brief for live patient"
    assert result.reasoning_trace is not None
