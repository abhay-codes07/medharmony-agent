#!/bin/bash
# =============================================================================
# MedHarmony — Pre-Deployment Validation Script
# =============================================================================
# Runs a series of checks to confirm the agent is ready for production.
# Exit code 0 = ready, non-zero = not ready (with clear error message).
#
# Usage:
#   bash scripts/deploy_check.sh
#   bash scripts/deploy_check.sh --skip-demo    # skip the full analysis test
# =============================================================================

set -euo pipefail

SKIP_DEMO=false
for arg in "$@"; do
    [[ "$arg" == "--skip-demo" ]] && SKIP_DEMO=true
done

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASS=0
FAIL=0

pass() { echo -e "  ${GREEN}✓ PASS${NC}  $1"; ((PASS++)); }
fail() { echo -e "  ${RED}✗ FAIL${NC}  $1"; ((FAIL++)); }
info() { echo -e "  ${BLUE}ℹ${NC}  $1"; }

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  MedHarmony Pre-Deployment Validation        ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════╝${NC}"
echo ""

# ---------------------------------------------------------------------------
# Check 1: Required environment variables
# ---------------------------------------------------------------------------
echo "[ 1/5 ] Checking environment variables..."

if [[ -n "${GEMINI_API_KEY:-}" ]]; then
    pass "GEMINI_API_KEY is set"
else
    fail "GEMINI_API_KEY is not set — export GEMINI_API_KEY=<your-key>"
fi

if [[ -n "${A2A_AGENT_URL:-}" ]]; then
    pass "A2A_AGENT_URL is set → ${A2A_AGENT_URL}"
else
    info "A2A_AGENT_URL not set — will default to http://localhost:8000"
fi

# ---------------------------------------------------------------------------
# Check 2: Python dependencies installed
# ---------------------------------------------------------------------------
echo ""
echo "[ 2/5 ] Checking Python dependencies..."

if python3 -c "import fastapi, google.genai, mcp, jinja2, httpx, loguru" 2>/dev/null; then
    pass "All core Python packages importable"
else
    fail "Missing Python dependencies — run: pip install -r requirements.txt"
fi

if python3 -c "from src.agent.config import GEMINI_API_KEY, A2A_AGENT_URL" 2>/dev/null; then
    pass "src.agent.config loads successfully"
else
    fail "src.agent.config import failed — check project structure"
fi

# ---------------------------------------------------------------------------
# Check 3: Start the agent server in background, test /health and agent card
# ---------------------------------------------------------------------------
echo ""
echo "[ 3/5 ] Starting agent server and checking endpoints..."

# Kill any existing server on port 8000
pkill -f "src.agent.server" 2>/dev/null || true
sleep 1

# Start server in background
python3 -m src.agent.server &
SERVER_PID=$!
info "Started server (PID: $SERVER_PID) — waiting for startup..."
sleep 4

# Cleanup on exit
cleanup() {
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

# Health check
HEALTH=$(curl -sf http://localhost:8000/health 2>/dev/null || echo "FAILED")
if echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('status')=='healthy' else 1)" 2>/dev/null; then
    pass "/health endpoint returns 200 with status=healthy"
else
    fail "/health endpoint check failed: $HEALTH"
fi

# Agent card check
AGENT_CARD=$(curl -sf http://localhost:8000/.well-known/agent.json 2>/dev/null || echo "FAILED")
if echo "$AGENT_CARD" | python3 -c "
import sys, json
card = json.load(sys.stdin)
assert card.get('name'), 'Missing name'
assert card.get('url'), 'Missing url'
assert len(card.get('skills', [])) >= 4, 'Expected 4 skills'
assert card.get('extensions', {}).get('sharp', {}).get('supportsPatientContext'), 'Missing SHARP'
" 2>/dev/null; then
    pass "Agent card (/.well-known/agent.json) — valid A2A card with SHARP extension"
else
    fail "Agent card check failed: $AGENT_CARD"
fi

# ---------------------------------------------------------------------------
# Check 4: MCP servers can be imported
# ---------------------------------------------------------------------------
echo ""
echo "[ 4/5 ] Checking MCP server modules..."

for module in \
    "src.mcp_servers.fhir_server.server" \
    "src.mcp_servers.drug_interaction_server.server" \
    "src.mcp_servers.clinical_guidelines_server.server"; do
    if python3 -c "import $module" 2>/dev/null; then
        pass "MCP module importable: $module"
    else
        fail "MCP module import failed: $module"
    fi
done

# ---------------------------------------------------------------------------
# Check 5: End-to-end demo analysis
# ---------------------------------------------------------------------------
echo ""
echo "[ 5/5 ] End-to-end demo patient analysis..."

if [[ "$SKIP_DEMO" == "true" ]]; then
    info "Skipped (--skip-demo flag set)"
else
    ANALYSIS=$(curl -sf -X POST http://localhost:8000/api/analyze \
        -H "Content-Type: application/json" \
        -d '{"patient_id": "demo-001"}' \
        --max-time 120 2>/dev/null || echo "FAILED")

    if echo "$ANALYSIS" | python3 -c "
import sys, json
r = json.load(sys.stdin)
assert r.get('patient_id'), 'Missing patient_id'
assert r.get('clinician_brief'), 'Missing clinician_brief'
assert isinstance(r.get('reconciliation'), list), 'Missing reconciliation'
assert isinstance(r.get('interactions'), list), 'Missing interactions'
total = r.get('total_medications', 0)
assert total > 0, f'Expected >0 medications, got {total}'
print(f'    Patient: {r[\"patient_name\"]} | Meds: {total} | Critical: {r[\"critical_issues\"]} | High: {r[\"high_issues\"]}')
" 2>/dev/null; then
        pass "Demo analysis complete — structured result returned"
    else
        fail "Demo analysis failed: $(echo "$ANALYSIS" | head -c 300)"
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "────────────────────────────────────────────"
TOTAL=$((PASS + FAIL))
echo -e "  Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC} / ${TOTAL} checks"

if [[ $FAIL -eq 0 ]]; then
    echo ""
    echo -e "  ${GREEN}✅ MedHarmony is ready for deployment!${NC}"
    echo ""
    echo "  Deploy to Render:"
    echo "    1. Push to GitHub: git push origin main"
    echo "    2. Connect repo at https://render.com/new"
    echo "    3. Use render.yaml for one-click config"
    echo ""
    exit 0
else
    echo ""
    echo -e "  ${RED}❌ ${FAIL} check(s) failed — fix before deploying.${NC}"
    echo ""
    exit 1
fi
