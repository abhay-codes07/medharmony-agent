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

    async def detect_prescribing_cascades(
        self,
        patient_context: dict,
        medications: list[dict],
    ) -> str:
        """Detect prescribing cascades — chains where each drug treats a side effect
        of the previous one.

        This is multi-hop causal reasoning that pair-based interaction checkers
        can never find. Gemini is uniquely capable of it.

        Returns:
            Raw JSON string (list of cascade objects).
        """
        context = f"""PATIENT CONTEXT:
{json.dumps(patient_context, indent=2)}

ALL MEDICATIONS (combined from all lists):
{json.dumps(medications, indent=2)}"""

        prompt = """Analyze this medication list for PRESCRIBING CASCADES — chains where one
medication's side effect caused another medication to be prescribed, which may have
caused yet another to be prescribed, and so on.

COMMON REAL-WORLD CASCADE PATTERNS (use these as starting points, look for others too):
- CCB (amlodipine, diltiazem, nifedipine) → peripheral edema → loop diuretic (furosemide, torsemide)
  → electrolyte loss → potassium/magnesium supplement
- NSAID (ibuprofen, naproxen, diclofenac) → GI irritation / ulcer → PPI or H2 blocker
- ACE inhibitor → dry cough → antihistamine or cough suppressant
- Statin → myalgia → muscle relaxant or NSAID → (if NSAID) → GI protectant
- Bisphosphonate → esophageal irritation → PPI
- Corticosteroid → hyperglycemia → oral antidiabetic or insulin
- Opioid → constipation → laxative (and potentially opioid for pain from constipation)
- Antipsychotic → weight gain / metabolic syndrome → diabetes medication
- Beta-blocker → depression, fatigue → antidepressant
- Loop diuretic → hypokalemia → potassium supplement — BUT if patient is ALSO on
  ACE inhibitor + CKD → K+ is already elevated → potassium supplement worsens hyperkalemia

Pay special attention to DOUBLE-DIRECTION cascades where the correction itself
interacts with another condition (like the last example above).

For each cascade found, respond with JSON array (no markdown fences):
[{
  "chain": ["Root Drug", "Drug 2", "Drug 3"],
  "chain_description": "Plain English explanation of the full causal chain and why it matters",
  "root_medication": "Root Drug",
  "root_side_effect": "The specific side effect that triggered Drug 2",
  "cascade_depth": 2,
  "severity": "critical|high|moderate|low",
  "recommendation": "Which drugs in the chain could be stopped if the root cause is addressed or managed differently",
  "medications_to_review": ["Drug 2", "Drug 3"],
  "evidence_source": "Clinical reference"
}]

If no cascades found: []"""

        return await self.analyze(prompt, context)

    async def generate_patient_brief_data(
        self,
        patient_context: dict,
        reconciliation: list[dict],
        interactions: list[dict],
        deprescribing: list[dict],
        cascades: list[dict],
    ) -> dict:
        """Generate plain-language patient brief content for discharge counseling.

        Writes at 8th-grade reading level. Replaces medical jargon with plain English.
        Returns a structured dict consumed by the PatientBriefRenderer Jinja2 template.
        """
        # Only pass high/critical interactions for warning signs — don't overwhelm patient
        critical_interactions = [
            i for i in interactions if i.get("severity") in ("critical", "high")
        ]

        context = f"""PATIENT: {json.dumps(patient_context, indent=2)}

MEDICATION CHANGES (reconciliation):
{json.dumps(reconciliation, indent=2)}

CRITICAL SAFETY ISSUES:
{json.dumps(critical_interactions, indent=2)}

MEDICATIONS RECOMMENDED FOR REDUCTION:
{json.dumps([d for d in deprescribing if d.get("severity") in ("critical", "high")], indent=2)}"""

        prompt = """Write a plain-language medication summary for the patient to take home at discharge.
This replaces the confusing 10-page discharge paperwork most patients ignore.

WRITING RULES:
- 8th-grade reading level — no medical jargon
- Replace medical terms: "anticoagulant"→"blood thinner", "diuretic"→"water pill",
  "antihypertensive"→"blood pressure medicine", "eGFR/creatinine"→"kidney test",
  "benzodiazepine"→"nerve-calming pill", "NSAID"→"pain reliever like ibuprofen"
- Be warm and reassuring — but specific about danger signs
- Keep each explanation to 1-2 short sentences

Respond with JSON only (no markdown fences):
{
  "greeting": "One warm sentence for the patient about their discharge",
  "medications_continuing": [
    {"name": "Medication name", "plain_name": "What patients call it", "why": "1 sentence why they take it"}
  ],
  "medications_stopped": [
    {"name": "Medication name", "why_stopped": "Plain English reason. What to take instead if anything."}
  ],
  "medications_changed": [
    {"name": "Medication name", "what_changed": "dose/frequency change in plain words", "why": "why it changed"}
  ],
  "medications_new": [
    {"name": "Medication name", "plain_name": "Common name", "why": "1 sentence", "how_to_take": "When and how"}
  ],
  "warning_signs": [
    {"sign": "Specific observable sign or symptom", "action": "call your doctor / call 911 / go to ER immediately"}
  ],
  "important_dos_and_donts": [
    "Do NOT take ibuprofen, Advil, or Motrin — your doctor has switched you to Tylenol",
    "..."
  ],
  "follow_up_reminder": "When to follow up and why it matters in plain words"
}"""

        raw = await self.analyze(prompt, context, response_format="json")

        try:
            text = raw.strip()
            if "```json" in text:
                text = text.split("```json")[1]
            if "```" in text:
                text = text.split("```")[0]
            text = text.strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except Exception as exc:
            logger.warning(f"generate_patient_brief_data: parse failed: {exc}")

        return {}

    async def generate_clinician_brief(
        self,
        patient_context: dict,
        reconciliation: list[dict],
        interactions: list[dict],
        deprescribing: list[dict],
    ) -> dict:
        """Generate structured brief data for Jinja2 template rendering.

        Returns a dict (not freeform markdown) so that brief_templates.py
        can render consistent, professionally formatted output every time.

        The dict contains:
          - recommended_actions: list of specific action strings for the clinician
          - clinical_assessment: brief narrative summary of the overall situation

        The structural sections (reconciliation table, interaction findings, etc.)
        are rendered directly from the structured analysis data in BriefRenderer,
        so this method only generates the narrative/advisory content that benefits
        from LLM generation.

        Note: In the Week 3 pipeline, BriefRenderer.render() is called directly
        from ReconciliationEngine._generate_brief() using the already-parsed
        Python objects. This method is kept for backward compatibility and for
        use cases where only the structured brief data dict is needed.
        """
        context = f"""PATIENT: {json.dumps(patient_context, indent=2)}

RECONCILIATION RESULTS: {json.dumps(reconciliation, indent=2)}

INTERACTION ANALYSIS: {json.dumps(interactions, indent=2)}

DEPRESCRIBING RECOMMENDATIONS: {json.dumps(deprescribing, indent=2)}"""

        prompt = """Based on the medication analysis above, generate structured brief data.

Respond with a JSON object only (no markdown fences):
{
  "recommended_actions": [
    "Numbered action item 1 — specific, actionable, clinician-directed",
    "Numbered action item 2",
    "..."
  ],
  "clinical_assessment": "2-3 sentence narrative summary of the most important safety issues and overall medication burden for this patient"
}

Rules:
- Each recommended_action must be specific and actionable (not generic)
- Prioritise critical and high-severity issues first
- Never make autonomous clinical decisions — frame as recommendations for clinician review
- clinical_assessment should be scannable in under 30 seconds"""

        raw = await self.analyze(prompt, context, response_format="json")

        # Parse the structured response
        try:
            text = raw.strip()
            if "```json" in text:
                text = text.split("```json")[1]
            if "```" in text:
                text = text.split("```")[0]
            text = text.strip()

            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                return {
                    "recommended_actions": data.get("recommended_actions", []),
                    "clinical_assessment": data.get("clinical_assessment", ""),
                }
        except Exception as exc:
            logger.warning(f"generate_clinician_brief: failed to parse structured response: {exc}")

        # Fallback: return empty structure (BriefRenderer uses result.tasks instead)
        return {"recommended_actions": [], "clinical_assessment": ""}
