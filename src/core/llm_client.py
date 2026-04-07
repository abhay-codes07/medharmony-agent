"""Gemini LLM client for MedHarmony clinical reasoning."""

from __future__ import annotations

import json
from typing import Any, Callable, Coroutine, Optional

from google import genai
from google.genai import types
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.agent.config import GEMINI_API_KEY, GEMINI_MODEL

# Max iterations for the agentic tool-use loop before returning whatever we have
_MAX_TOOL_ITERATIONS = 10


class LLMClient:
    """Wrapper around the Google Gemini API for clinical reasoning.

    Provides both plain text completion (analyze) and an agentic tool-use loop
    (analyze_with_tools) where Gemini autonomously decides which MCP tools to
    call, in what order, until it produces a final text response.
    """

    def __init__(self):
        # NOTE: GEMINI_API_KEY must be set in .env.  If empty the client will
        # still construct but every call will raise an authentication error.
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model = GEMINI_MODEL
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

    # -------------------------------------------------------------------------
    # Core completion method (plain text, no tools)
    # -------------------------------------------------------------------------

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
        """Send a clinical analysis prompt to Gemini.

        Args:
            prompt: The clinical reasoning prompt.
            context: Optional patient context to prepend as prior conversation turns.
            response_format: "json" or "markdown" — used only to set expectations
                in the prompt (Gemini does not have a native JSON mode flag in this SDK).

        Returns:
            The model's text response.
        """
        contents: list[types.Content] = []

        if context:
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(context)],
                )
            )
            contents.append(
                types.Content(
                    role="model",
                    parts=[types.Part.from_text(
                        "I have received the patient context. Ready for analysis."
                    )],
                )
            )

        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(prompt)],
            )
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    temperature=0.2,
                    max_output_tokens=4096,
                ),
            )

            result = response.text
            logger.debug(f"Gemini response length: {len(result)} chars")
            return result

        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise

    # -------------------------------------------------------------------------
    # Agentic tool-use loop
    # -------------------------------------------------------------------------

    async def analyze_with_tools(
        self,
        prompt: str,
        tools: list[types.Tool],
        tool_executor: Callable[[str, dict], Coroutine[Any, Any, str]],
        context: Optional[str] = None,
    ) -> str:
        """Run an agentic reasoning loop: Gemini decides which tools to call.

        Sends the prompt + available tools to Gemini.  If Gemini responds with
        function calls, executes them via ``tool_executor``, appends the results,
        and calls Gemini again.  Loops until Gemini returns a pure text response
        or ``_MAX_TOOL_ITERATIONS`` is reached.

        Args:
            prompt: The clinical reasoning prompt.
            tools: List of ``types.Tool`` objects (Gemini function declarations).
            tool_executor: Async callable ``(tool_name, arguments) -> str``
                that routes the call to the correct MCP server.
            context: Optional prior context string (prepended as user/model turns).

        Returns:
            The model's final text response.
        """
        contents: list[types.Content] = []

        if context:
            contents.append(
                types.Content(role="user", parts=[types.Part.from_text(context)])
            )
            contents.append(
                types.Content(
                    role="model",
                    parts=[types.Part.from_text(
                        "I have received the patient context. Ready for analysis."
                    )],
                )
            )

        contents.append(
            types.Content(role="user", parts=[types.Part.from_text(prompt)])
        )

        for iteration in range(_MAX_TOOL_ITERATIONS):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=self.system_prompt,
                        tools=tools,
                        temperature=0.2,
                        max_output_tokens=4096,
                    ),
                )
            except Exception as e:
                logger.error(f"Gemini API error (iteration {iteration}): {e}")
                raise

            candidate = response.candidates[0]

            # Collect function calls from this response turn
            function_calls = [
                part.function_call
                for part in candidate.content.parts
                if part.function_call
            ]

            if not function_calls:
                # No more tool calls — return the final text
                logger.debug(
                    f"Gemini finished after {iteration} tool iterations; "
                    f"response length: {len(response.text)} chars"
                )
                return response.text

            logger.info(
                f"[tool-loop] iteration={iteration}, "
                f"tool_calls={[fc.name for fc in function_calls]}"
            )

            # Append the model's function-call turn to the conversation
            contents.append(candidate.content)

            # Execute each function call and collect responses
            tool_response_parts: list[types.Part] = []
            for fc in function_calls:
                tool_name = fc.name
                tool_args = dict(fc.args)

                logger.info(f"  → calling tool: {tool_name}({tool_args})")
                try:
                    result_text = await tool_executor(tool_name, tool_args)
                except Exception as exc:
                    result_text = json.dumps({"error": str(exc), "tool": tool_name})
                    logger.warning(f"  ✗ {tool_name} failed: {exc}")
                else:
                    logger.info(f"  ✓ {tool_name} returned {len(result_text)} chars")

                tool_response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=tool_name,
                            response={"result": result_text},
                        )
                    )
                )

            # Append tool responses as a user turn (Gemini convention)
            contents.append(
                types.Content(role="user", parts=tool_response_parts)
            )

        # Exhausted max iterations — do a final call without tools
        logger.warning(
            f"Reached max tool iterations ({_MAX_TOOL_ITERATIONS}); "
            "calling Gemini without tools to force a text response."
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=self.system_prompt,
                temperature=0.2,
                max_output_tokens=4096,
            ),
        )
        return response.text

    # -------------------------------------------------------------------------
    # Convenience wrappers (unchanged public interface)
    # -------------------------------------------------------------------------

    async def reconcile_medications(
        self,
        patient_context: dict,
        medication_lists: list[dict],
    ) -> str:
        """Ask Gemini to reconcile medication lists."""
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
        """Ask Gemini to analyze drug interactions in patient context."""
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
        """Ask Gemini for deprescribing recommendations."""
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
