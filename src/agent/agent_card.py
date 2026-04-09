"""A2A Agent Card for MedHarmony.

The Agent Card is a JSON document that describes the agent's capabilities,
skills, and endpoint. It's fetched by the Prompt Opinion platform and other
agents to discover what MedHarmony can do.

Week 3 additions:
- A2A_AGENT_URL now fully configurable via environment variable
- iconUrl field for project logo
- documentationUrl pointing to GitHub repo
- Fully populated SHARP extensions block
"""

import os

from src.agent.config import A2A_AGENT_NAME, A2A_AGENT_URL


def get_agent_card() -> dict:
    """Return the A2A Agent Card for MedHarmony."""
    # Allow runtime override of URL for deployed instances
    agent_url = os.getenv("A2A_AGENT_URL", A2A_AGENT_URL).rstrip("/")
    github_url = os.getenv(
        "GITHUB_REPO_URL",
        "https://github.com/abhay-codes07/medharmony-agent",
    )
    icon_url = os.getenv("AGENT_ICON_URL", f"{github_url}/raw/main/docs/logo.png")

    return {
        "name": A2A_AGENT_NAME,
        "description": (
            "MedHarmony is an intelligent medication reconciliation and safety agent. "
            "It analyzes patient medication lists across care transitions, identifies "
            "dangerous drug interactions, flags contraindications based on patient-specific "
            "lab values and conditions, suggests evidence-based deprescribing opportunities "
            "(Beers Criteria 2023, STOPP/START v3), and generates clinician-ready safety "
            "briefs — all grounded in real FHIR R4 patient data."
        ),
        "url": agent_url,
        "version": "1.0.0",
        "iconUrl": icon_url,
        "documentationUrl": f"{github_url}#readme",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
        },
        "skills": [
            {
                "id": "medication-reconciliation",
                "name": "Medication Reconciliation",
                "description": (
                    "Compares medication lists across care settings (admission, discharge, "
                    "outpatient) and identifies discrepancies, duplications, omissions, and "
                    "dose changes. Produces a reconciled list with clinical rationale."
                ),
                "tags": [
                    "medication", "reconciliation", "patient-safety",
                    "care-transition", "discharge",
                ],
                "examples": [
                    "Reconcile this patient's medications between admission and discharge",
                    "Compare home meds with inpatient orders and flag discrepancies",
                    "Generate a reconciled medication list for discharge",
                ],
            },
            {
                "id": "drug-interaction-analysis",
                "name": "Drug Interaction Analysis",
                "description": (
                    "Analyzes all active medications for drug-drug, drug-condition, "
                    "drug-allergy, and drug-lab interactions. Considers patient-specific "
                    "factors like renal function, age, and comorbidities via RxNorm and "
                    "OpenFDA APIs through MCP tool integration."
                ),
                "tags": [
                    "drug-interaction", "safety", "pharmacology",
                    "contraindication", "allergy", "rxnorm", "openfda",
                ],
                "examples": [
                    "Check for drug interactions in this patient's medication list",
                    "Are any of this patient's medications contraindicated given their CKD?",
                    "Flag medications that need renal dose adjustment",
                ],
            },
            {
                "id": "deprescribing-advisor",
                "name": "Deprescribing Advisor",
                "description": (
                    "Identifies medications that may be appropriate to deprescribe using "
                    "AGS Beers Criteria 2023, STOPP/START v3, and evidence-based "
                    "deprescribing protocols. Provides tapering plans and alternatives."
                ),
                "tags": [
                    "deprescribing", "polypharmacy", "beers-criteria",
                    "elderly", "geriatrics", "stopp-start",
                ],
                "examples": [
                    "Review this 78-year-old's medications for deprescribing opportunities",
                    "Apply Beers Criteria to this patient's medication list",
                    "Suggest a tapering plan for benzodiazepine deprescribing",
                ],
            },
            {
                "id": "clinician-safety-brief",
                "name": "Clinician Safety Brief",
                "description": (
                    "Generates a concise, actionable medication safety brief combining "
                    "reconciliation results, interaction alerts, and deprescribing "
                    "recommendations into a single clinician-ready document formatted "
                    "with a professional Jinja2 template."
                ),
                "tags": [
                    "brief", "report", "clinical-decision-support", "summary",
                ],
                "examples": [
                    "Generate a medication safety brief for this patient",
                    "Create a discharge medication safety summary",
                    "Produce a concise med safety report for the care team",
                ],
            },
        ],
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "provider": {
            "organization": "MedHarmony",
            "url": github_url,
        },
        "authentication": {
            "schemes": ["none"],  # Will be enhanced for production
        },
        # SHARP Extension — Prompt Opinion healthcare context propagation
        "extensions": {
            "sharp": {
                "supportsPatientContext": True,
                "supportsCohortContext": False,
                "supportsResearchContext": False,
                "requiredFhirResources": [
                    "Patient",
                    "MedicationRequest",
                    "MedicationStatement",
                    "AllergyIntolerance",
                    "Condition",
                    "Observation",
                ],
                "optionalFhirResources": [
                    "Encounter",
                    "Practitioner",
                    "Organization",
                ],
                "fhirVersion": "R4",
                "contextFields": {
                    "patient_id": "FHIR Patient resource ID",
                    "fhir_server_url": "Base URL of the FHIR server (default: hapi.fhir.org)",
                    "fhir_access_token": "Optional Bearer token for authenticated FHIR servers",
                    "encounter_id": "Optional current Encounter ID for context",
                    "user_role": "Role of the requesting clinician (pharmacist, physician, etc.)",
                    "organization_id": "Optional organisation ID for audit logging",
                },
                "responseArtifacts": [
                    {
                        "name": "clinician_safety_brief",
                        "mimeType": "text/markdown",
                        "description": "Jinja2-rendered clinician safety brief",
                    },
                    {
                        "name": "analysis_data",
                        "mimeType": "application/json",
                        "description": "Structured analysis with reconciliation, interactions, deprescribing",
                    },
                    {
                        "name": "reasoning_trace",
                        "mimeType": "application/json",
                        "description": "Full agent reasoning trace for observability",
                    },
                ],
            }
        },
    }
