"""A2A Agent Card for MedHarmony.

The Agent Card is a JSON document that describes the agent's capabilities,
skills, and endpoint. It's fetched by the Prompt Opinion platform and other
agents to discover what MedHarmony can do.
"""

from src.agent.config import A2A_AGENT_URL, A2A_AGENT_NAME


def get_agent_card() -> dict:
    """Return the A2A Agent Card for MedHarmony."""
    return {
        "name": A2A_AGENT_NAME,
        "description": (
            "MedHarmony is an intelligent medication reconciliation and safety agent. "
            "It analyzes patient medication lists across care transitions, identifies "
            "dangerous drug interactions, flags contraindications based on patient-specific "
            "lab values and conditions, suggests evidence-based deprescribing opportunities, "
            "and generates clinician-ready safety briefs — all grounded in FHIR patient data."
        ),
        "url": A2A_AGENT_URL,
        "version": "1.0.0",
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
                    "factors like renal function, age, and comorbidities."
                ),
                "tags": [
                    "drug-interaction", "safety", "pharmacology",
                    "contraindication", "allergy",
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
                    "elderly", "geriatrics",
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
                    "recommendations into a single clinician-ready document."
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
            "url": "https://github.com/YOUR_USERNAME/medharmony-agent",
        },
        "authentication": {
            "schemes": ["none"],  # Will be enhanced for production
        },
        # SHARP Extension - Prompt Opinion healthcare context
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
                "fhirVersion": "R4",
            }
        },
    }
