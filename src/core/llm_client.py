"""Claude LLM client for MedHarmony clinical reasoning."""

from __future__ import annotations

import json
from typing import Optional

import anthropic
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.agent.config import ANTHROPIC_API_KEY, CLAUDE_MODEL


class LLMClient:
    """Wrapper around the Anthropic Claude API for clinical reasoning."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model = CLAUDE_MODEL
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        return """You are MedHarmony, a clinical AI agent specialized in medication safety and reconciliation.

Your role is to assist clinicians by:
1. Reconciling medication lists across care transitions
2. Identifying drug-drug, drug-condition, drug-allergy, and drug-lab interactions
3. Recommending evidence-based deprescribing using Beers Criteria and STOPP/START
4. Generating clear, actionable clinician safety briefs

CRITICAL RULES:
- Always ground your reasoning in the patient data provided
- Cite specific clinical evidence for every recommendation
- Flag severity levels accurately: CRITICAL (immediate harm risk), HIGH (significant risk), MODERATE (monitor), LOW (minor concern)
- Never make autonomous clinical decisions — always frame as recommendations for clinician review
- Use standard medical terminology
- When uncertain, explicitly state uncertainty and recommend further review
- Consider renal function (eGFR/creatinine), hepatic function, age, weight, and allergies for every medication assessment

OUTPUT FORMAT: Always respond with structured JSON when asked for analysis results."""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def analyze(
        self,
        prompt: str,
        context: Optional[str] = None,
        response_format: str = "json",
    ) -> str:
        """Send a clinical analysis prompt to Claude."""
        messages = []

        if context:
            messages.append({"role": "user", "content": context})
            messages.append({
                "role": "assistant",
                "content": "I have received the patient context. Ready for analysis."
            })

        messages.append({"role": "user", "content": prompt})

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                messages=messages,
            )

            result = response.content[0].text
            logger.debug(f"LLM response length: {len(result)} chars")
            return result

        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            raise

    async def reconcile_medications(
        self,
        patient_context: dict,
        medication_lists: list[dict],
    ) -> str:
        """Ask Claude to reconcile medication lists."""
        context = f"""PATIENT CONTEXT:
{json.dumps(patient_context, indent=2)}

MEDICATION LISTS TO RECONCILE:
{json.dumps(medication_lists, indent=2)}"""

        prompt = """Analyze the medication lists above and perform a complete reconciliation.

For each medication across all lists, determine:
1. Should it be CONTINUED, DISCONTINUED, MODIFIED, SUBSTITUTED, ADDED, or HELD?
2. Why? Provide clinical reasoning.
3. Are there any discrepancies between lists?

Respond with a JSON array of reconciliation entries:
```json
[
  {
    "medication": "Drug Name",
    "action": "continue|discontinue|modify-dose|substitute|add|hold|review",
    "reason": "Clinical reasoning",
    "from_source": "which list this came from",
    "current_dose": "current dosing",
    "recommended_dose": "recommended dosing if changed",
    "notes": "additional notes"
  }
]
```"""
        return await self.analyze(prompt, context)

    async def analyze_interactions(
        self,
        patient_context: dict,
        medications: list[dict],
        known_interactions: list[dict],
    ) -> str:
        """Ask Claude to analyze drug interactions in patient context."""
        context = f"""PATIENT CONTEXT:
{json.dumps(patient_context, indent=2)}

ACTIVE MEDICATIONS:
{json.dumps(medications, indent=2)}

KNOWN INTERACTIONS FROM DATABASE:
{json.dumps(known_interactions, indent=2)}"""

        prompt = """Analyze ALL interactions for this specific patient, considering their unique clinical context (age, renal function, hepatic function, conditions, allergies, current lab values).

Go beyond the database interactions — use your clinical knowledge to identify:
1. Drug-drug interactions (including pharmacokinetic and pharmacodynamic)
2. Drug-condition contraindications
3. Drug-allergy cross-reactivity risks
4. Drug-lab interactions (e.g., medication affecting a lab value that's already abnormal)
5. Duplicate therapy / therapeutic overlap

For each interaction found, respond with JSON:
```json
[
  {
    "type": "drug-drug|drug-condition|drug-allergy|drug-lab|duplicate-therapy",
    "severity": "critical|high|moderate|low",
    "drug_a": "First drug",
    "drug_b": "Second drug (if drug-drug)",
    "condition": "Condition name (if drug-condition)",
    "allergy": "Allergy (if drug-allergy)",
    "lab": "Lab name (if drug-lab)",
    "description": "What the interaction is",
    "clinical_significance": "Why it matters for THIS patient",
    "recommendation": "What the clinician should do",
    "evidence_source": "Guideline or evidence reference"
  }
]
```"""
        return await self.analyze(prompt, context)

    async def suggest_deprescribing(
        self,
        patient_context: dict,
        medications: list[dict],
        guideline_excerpts: list[dict],
    ) -> str:
        """Ask Claude for deprescribing recommendations."""
        context = f"""PATIENT CONTEXT:
{json.dumps(patient_context, indent=2)}

CURRENT MEDICATIONS:
{json.dumps(medications, indent=2)}

RELEVANT GUIDELINE EXCERPTS:
{json.dumps(guideline_excerpts, indent=2)}"""

        prompt = """Based on the patient's age, conditions, renal function, and current medications, identify medications that should be considered for deprescribing.

Apply:
- AGS Beers Criteria (2023) for patients ≥65
- STOPP/START Criteria v3
- General polypharmacy reduction principles

For each recommendation, provide JSON:
```json
[
  {
    "medication": "Drug Name",
    "criteria": "Which guideline applies",
    "reason": "Why this med should be reviewed",
    "recommendation": "Specific recommendation (taper, stop, substitute)",
    "severity": "critical|high|moderate|low",
    "tapering_plan": "Step-down plan if applicable",
    "alternatives": ["Alternative 1", "Alternative 2"]
  }
]
```"""
        return await self.analyze(prompt, context)

    async def generate_clinician_brief(
        self,
        patient_context: dict,
        reconciliation: list[dict],
        interactions: list[dict],
        deprescribing: list[dict],
    ) -> str:
        """Generate a concise clinician safety brief."""
        context = f"""PATIENT: {json.dumps(patient_context, indent=2)}

RECONCILIATION RESULTS: {json.dumps(reconciliation, indent=2)}

INTERACTION ANALYSIS: {json.dumps(interactions, indent=2)}

DEPRESCRIBING RECOMMENDATIONS: {json.dumps(deprescribing, indent=2)}"""

        prompt = """Generate a concise clinician safety brief in Markdown format.

Structure:
# MedHarmony Safety Brief
**Patient:** [Name] | **Age:** [X] | **Date:** [Today]

## ⚠️ Critical Alerts (if any)
- List critical items requiring immediate attention

## 📋 Medication Reconciliation Summary
- Key changes table: Medication | Action | Reason

## 💊 Interaction Alerts
- Grouped by severity

## 📉 Deprescribing Opportunities
- Evidence-based recommendations

## ✅ Recommended Actions
- Numbered list of concrete next steps

## 📊 Summary
- Total meds: X | Critical: X | High: X | Moderate: X

Keep it actionable and scannable. Clinicians have 30 seconds to review this."""

        return await self.analyze(prompt, context, response_format="markdown")
