"""SHARP Extension Context handler for Prompt Opinion integration.

SHARP specs propagate healthcare context (patient IDs, FHIR tokens)
through multi-agent call chains on the Prompt Opinion platform.
"""

from __future__ import annotations

from typing import Optional

from loguru import logger

from src.models.medication import SharpContext


def extract_sharp_context(metadata: dict) -> SharpContext:
    """Extract SHARP context from A2A task metadata or message parts.

    The Prompt Opinion platform passes SHARP context via:
    1. Task metadata (preferred)
    2. Message parts with specific MIME types
    3. Extension headers in the A2A request

    Args:
        metadata: The A2A task metadata dict or message context.

    Returns:
        SharpContext with extracted values.
    """
    context = SharpContext()

    # Method 1: Direct metadata fields (PO platform standard)
    sharp_data = metadata.get("sharp", {})
    if not sharp_data:
        # Try alternate key paths
        sharp_data = metadata.get("context", {}).get("sharp", {})

    if sharp_data:
        context.patient_id = sharp_data.get("patient_id") or sharp_data.get("patientId")
        context.fhir_server_url = sharp_data.get("fhir_server_url") or sharp_data.get("fhirServerUrl")
        context.fhir_access_token = sharp_data.get("fhir_access_token") or sharp_data.get("fhirAccessToken")
        context.encounter_id = sharp_data.get("encounter_id") or sharp_data.get("encounterId")
        context.user_role = sharp_data.get("user_role") or sharp_data.get("userRole")
        context.organization_id = sharp_data.get("organization_id") or sharp_data.get("organizationId")

    # Method 2: Flat metadata keys (fallback)
    if not context.patient_id:
        context.patient_id = metadata.get("patient_id") or metadata.get("patientId")
    if not context.fhir_server_url:
        context.fhir_server_url = metadata.get("fhir_server_url") or metadata.get("fhirServerUrl")
    if not context.fhir_access_token:
        context.fhir_access_token = metadata.get("fhir_access_token") or metadata.get("fhirAccessToken")

    # Method 3: FHIR launch context (SMART on FHIR style)
    launch_context = metadata.get("fhirContext", [])
    if isinstance(launch_context, list):
        for item in launch_context:
            if isinstance(item, dict):
                ref = item.get("reference", "")
                if ref.startswith("Patient/") and not context.patient_id:
                    context.patient_id = ref.replace("Patient/", "")
                elif ref.startswith("Encounter/") and not context.encounter_id:
                    context.encounter_id = ref.replace("Encounter/", "")

    if context.patient_id:
        logger.info(f"SHARP context extracted — Patient: {context.patient_id}")
    else:
        logger.warning("No patient ID found in SHARP context")

    return context


def build_sharp_response_metadata(context: SharpContext) -> dict:
    """Build SHARP metadata to include in A2A response.

    This propagates context back through the chain so downstream
    agents can continue operating in the same patient context.
    """
    return {
        "sharp": {
            "patient_id": context.patient_id,
            "fhir_server_url": context.fhir_server_url,
            "encounter_id": context.encounter_id,
            "organization_id": context.organization_id,
        }
    }
