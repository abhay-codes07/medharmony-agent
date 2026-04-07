#!/usr/bin/env bash
# MedHarmony Agentic Demo
#
# Runs a full medication safety analysis for the built-in demo patient
# (Margaret Thompson, 78F, CKD Stage 3b, 12 medications) and streams
# the complete MCP tool-call trace to stdout.
#
# Usage:
#   ./scripts/demo.sh
#   GEMINI_API_KEY=your-key ./scripts/demo.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT"

# ── Check environment ──────────────────────────────────────────────────────────
if [ -f ".env" ]; then
  # shellcheck disable=SC2046
  export $(grep -v '^#' .env | xargs) 2>/dev/null || true
fi

if [ -z "${GEMINI_API_KEY:-}" ]; then
  echo "⚠  GEMINI_API_KEY is not set."
  echo "   The demo will still run but LLM calls will fail with an auth error."
  echo "   Set it with: export GEMINI_API_KEY=your-key"
  echo ""
fi

# ── Run demo ───────────────────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           MedHarmony Agentic Tool-Call Demo                  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Patient:  Margaret Thompson, 78F"
echo "Context:  CKD Stage 3b (eGFR 32) | Atrial Fibrillation | T2DM"
echo "          12 medications across admission + discharge lists"
echo ""
echo "Agentic tool calls will be traced below as they execute..."
echo "──────────────────────────────────────────────────────────────"
echo ""

python3 - <<'PYEOF'
import asyncio
import sys
from loguru import logger

# Pretty console trace — show tool-loop calls prominently
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | {message}",
    colorize=True,
    level="INFO",
)

from src.core.reconciliation import ReconciliationEngine
from src.models.medication import SharpContext


async def main() -> None:
    engine = ReconciliationEngine()

    # Use a patient_id that will trigger the demo fallback
    # (no live FHIR server needed for demo)
    context = SharpContext(
        patient_id="demo-001",
        encounter_id="demo-enc-001",
    )

    result = await engine.run_full_analysis(context)

    print("\n" + "═" * 62)
    print("  ANALYSIS RESULTS")
    print("═" * 62)
    print(f"  Patient:              {result.patient_name}")
    print(f"  Total medications:    {result.total_medications}")
    print(f"  Critical issues:      {result.critical_issues}")
    print(f"  High issues:          {result.high_issues}")
    print(f"  Moderate issues:      {result.moderate_issues}")
    print(f"  Reconciliation items: {len(result.reconciliation)}")
    print(f"  Interactions found:   {len(result.interactions)}")
    print(f"  Deprescribing opps:   {len(result.deprescribing)}")
    print("═" * 62)

    if result.tasks:
        print(f"\n  Follow-up Tasks ({len(result.tasks)}):")
        for task in result.tasks:
            print(f"    • {task}")

    if result.clinician_brief:
        print("\n" + "─" * 62)
        print("  CLINICIAN BRIEF (excerpt):")
        print("─" * 62)
        brief = result.clinician_brief
        print(brief[:1200] + "\n  [... truncated ...]" if len(brief) > 1200 else brief)

    print("\n  ✓ Demo complete\n")


asyncio.run(main())
PYEOF
