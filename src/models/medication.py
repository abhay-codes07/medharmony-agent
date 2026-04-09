"""Data models for MedHarmony Agent."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    INFO = "info"


class InteractionType(str, Enum):
    DRUG_DRUG = "drug-drug"
    DRUG_CONDITION = "drug-condition"
    DRUG_ALLERGY = "drug-allergy"
    DRUG_LAB = "drug-lab"
    DUPLICATE_THERAPY = "duplicate-therapy"


class ReconciliationAction(str, Enum):
    CONTINUE = "continue"
    DISCONTINUE = "discontinue"
    MODIFY_DOSE = "modify-dose"
    SUBSTITUTE = "substitute"
    ADD = "add"
    HOLD = "hold"
    REVIEW = "review"


class CareTransitionType(str, Enum):
    ADMISSION = "admission"
    DISCHARGE = "discharge"
    TRANSFER = "transfer"
    OUTPATIENT_VISIT = "outpatient-visit"


# =============================================================================
# Medication Models
# =============================================================================

class Medication(BaseModel):
    """A single medication entry."""
    id: str = ""
    name: str
    rxnorm_code: Optional[str] = None
    dose: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = None
    status: str = "active"
    prescriber: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    source: str = "unknown"  # e.g., "admission", "discharge", "outpatient"
    fhir_resource_id: Optional[str] = None


class MedicationList(BaseModel):
    """A list of medications from a specific source/setting."""
    source: str  # "admission", "discharge", "home", "outpatient"
    timestamp: Optional[str] = None
    medications: list[Medication] = []


# =============================================================================
# Patient Context Models
# =============================================================================

class Allergy(BaseModel):
    """Patient allergy record."""
    substance: str
    reaction: Optional[str] = None
    severity: Optional[str] = None
    fhir_resource_id: Optional[str] = None


class Condition(BaseModel):
    """Patient condition/diagnosis."""
    name: str
    icd10_code: Optional[str] = None
    status: str = "active"
    onset_date: Optional[str] = None
    fhir_resource_id: Optional[str] = None


class LabResult(BaseModel):
    """A lab observation."""
    name: str
    loinc_code: Optional[str] = None
    value: float
    unit: str
    reference_range: Optional[str] = None
    date: Optional[str] = None
    is_abnormal: bool = False
    fhir_resource_id: Optional[str] = None


class PatientContext(BaseModel):
    """Full patient context pulled from FHIR."""
    patient_id: str
    name: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    weight_kg: Optional[float] = None
    allergies: list[Allergy] = []
    conditions: list[Condition] = []
    lab_results: list[LabResult] = []
    medication_lists: list[MedicationList] = []
    fhir_server_url: Optional[str] = None


# =============================================================================
# Analysis Result Models
# =============================================================================

class DrugInteraction(BaseModel):
    """A detected drug interaction."""
    type: InteractionType
    severity: Severity
    drug_a: str
    drug_b: Optional[str] = None  # None for drug-condition/allergy
    condition: Optional[str] = None
    allergy: Optional[str] = None
    lab: Optional[str] = None
    description: str
    clinical_significance: str
    recommendation: str
    evidence_source: Optional[str] = None


class DeprescribingRecommendation(BaseModel):
    """A recommendation to reduce/stop a medication."""
    medication: str
    criteria: str  # e.g., "Beers Criteria 2023", "STOPP v3"
    reason: str
    recommendation: str
    severity: Severity
    tapering_plan: Optional[str] = None
    alternatives: list[str] = []


class ReconciliationEntry(BaseModel):
    """A single reconciliation decision."""
    medication: str
    action: ReconciliationAction
    reason: str
    from_source: Optional[str] = None
    current_dose: Optional[str] = None
    recommended_dose: Optional[str] = None
    notes: Optional[str] = None


class MedHarmonyResult(BaseModel):
    """Complete MedHarmony analysis result."""
    patient_id: str
    patient_name: Optional[str] = None
    analysis_timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )
    transition_type: Optional[CareTransitionType] = None

    # Core results
    reconciliation: list[ReconciliationEntry] = []
    interactions: list[DrugInteraction] = []
    deprescribing: list[DeprescribingRecommendation] = []

    # Summary stats
    total_medications: int = 0
    critical_issues: int = 0
    high_issues: int = 0
    moderate_issues: int = 0

    # Clinician brief (markdown, rendered via Jinja2 template in Week 3+)
    clinician_brief: str = ""

    # Follow-up tasks
    tasks: list[str] = []

    # Reasoning trace (Week 3 — full agent loop observability)
    reasoning_trace: Optional[dict] = None

    # Safety guard warnings (Week 3)
    safety_warnings: list[str] = []


# =============================================================================
# SHARP Context (Prompt Opinion integration)
# =============================================================================

class SharpContext(BaseModel):
    """SHARP extension context from Prompt Opinion."""
    patient_id: Optional[str] = None
    fhir_server_url: Optional[str] = None
    fhir_access_token: Optional[str] = None
    encounter_id: Optional[str] = None
    user_role: Optional[str] = None
    organization_id: Optional[str] = None


# =============================================================================
# A2A Protocol Models
# =============================================================================

class A2AMessage(BaseModel):
    """A2A protocol message."""
    role: str  # "user" or "agent"
    parts: list[dict]


class A2ATask(BaseModel):
    """A2A protocol task."""
    id: str
    status: str = "submitted"  # submitted, working, completed, failed
    messages: list[A2AMessage] = []
    artifacts: list[dict] = []
    metadata: dict = {}
