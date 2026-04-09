#!/bin/bash
# =============================================================================
# MedHarmony Agent - Test Script
# Tests the A2A endpoint with a demo patient + runs pytest unit/integration tests
#
# Usage:
#   bash scripts/test.sh [BASE_URL] [--integration] [--deploy-check]
#
# Flags:
#   --integration     Also run @pytest.mark.integration tests (hits live FHIR)
#   --deploy-check    Run scripts/deploy_check.sh at the end
# =============================================================================

set -e

BASE_URL="${1:-http://localhost:8000}"
RUN_INTEGRATION=false
RUN_DEPLOY_CHECK=false

# Parse flags (skip first positional arg)
for arg in "${@:2}"; do
    [[ "$arg" == "--integration" ]] && RUN_INTEGRATION=true
    [[ "$arg" == "--deploy-check" ]] && RUN_DEPLOY_CHECK=true
done

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}🧪 Testing MedHarmony Agent at ${BASE_URL}${NC}"
echo ""

# =============================================================================
# SECTION A: Pytest Unit Tests
# =============================================================================
echo -e "${BLUE}━━━ Section A: Pytest Unit Tests ━━━${NC}"

echo "  Running unit tests (excluding integration tests)..."
python3 -m pytest tests/ -v \
    --ignore=tests/test_real_fhir.py \
    -m "not integration" \
    --tb=short \
    2>&1 | tail -30

echo ""
echo -e "${GREEN}✅ Unit tests complete${NC}"
echo ""

# =============================================================================
# SECTION B: Integration Tests (optional)
# =============================================================================
if [[ "$RUN_INTEGRATION" == "true" ]]; then
    echo -e "${BLUE}━━━ Section B: Integration Tests (live FHIR) ━━━${NC}"
    echo -e "${YELLOW}  ⚠️  These tests make real network calls to hapi.fhir.org${NC}"
    echo ""

    python3 -m pytest tests/test_real_fhir.py -v \
        -m integration \
        --tb=short \
        2>&1 | tail -40

    echo ""
    echo -e "${GREEN}✅ Integration tests complete${NC}"
    echo ""
fi

# =============================================================================
# SECTION C: Live Server API Tests
# =============================================================================
echo -e "${BLUE}━━━ Section C: Live Server API Tests ━━━${NC}"

# Test 1: Health check
echo -e "${BLUE}Test 1: Health Check${NC}"
curl -s "$BASE_URL/health" | python3 -m json.tool
echo ""

# Test 2: Agent Card
echo -e "${BLUE}Test 2: Agent Card Discovery${NC}"
curl -s "$BASE_URL/.well-known/agent.json" | python3 -c "
import sys, json
card = json.load(sys.stdin)
print(f\"  Agent: {card['name']}\")
print(f\"  URL: {card['url']}\")
print(f\"  Skills: {len(card['skills'])}\")
for s in card['skills']:
    print(f\"    - {s['name']}: {s['description'][:60]}...\")
print(f\"  SHARP Patient Context: {card['extensions']['sharp']['supportsPatientContext']}\")
print(f\"  Response Artifacts: {len(card['extensions']['sharp'].get('responseArtifacts', []))}\")
"
echo ""

# Test 3: Direct API (demo patient)
echo -e "${BLUE}Test 3: Direct Analysis API (Demo Patient — Margaret Thompson 78F)${NC}"
echo "  Sending analysis request..."
echo ""

RESPONSE=$(curl -s -X POST "$BASE_URL/api/analyze" \
    -H "Content-Type: application/json" \
    -d '{"patient_id": "demo-001"}' \
    --max-time 120)

echo "$RESPONSE" | python3 -c "
import sys, json
r = json.load(sys.stdin)
print(f\"  Patient: {r.get('patient_name', 'N/A')}\")
print(f\"  Total Medications: {r['total_medications']}\")
print(f\"  🔴 Critical Issues: {r['critical_issues']}\")
print(f\"  🟠 High Issues: {r['high_issues']}\")
print(f\"  🟡 Moderate Issues: {r['moderate_issues']}\")
print(f\"  📋 Reconciliation Entries: {len(r['reconciliation'])}\")
print(f\"  💊 Interactions Found: {len(r['interactions'])}\")
print(f\"  📉 Deprescribing Recs: {len(r['deprescribing'])}\")
print(f\"  ✅ Tasks Generated: {len(r['tasks'])}\")

# Week 3 fields
trace = r.get('reasoning_trace') or {}
print(f\"  🔍 Trace Steps: {trace.get('step_count', 'N/A')}\")
print(f\"  ⏱️  Trace Duration: {trace.get('total_duration_ms', 'N/A')} ms\")
brief = r.get('clinician_brief', '')
print(f\"  📄 Brief Length: {len(brief)} chars\")
print(f\"  🛡️  Safety Warnings: {len(r.get('safety_warnings', []))}\")
print()
if r['tasks']:
    print('  Sample Tasks:')
    for t in r['tasks'][:3]:
        print(f'    • {t[:80]}...' if len(t) > 80 else f'    • {t}')
" 2>/dev/null || { echo -e "${RED}  Failed to parse response${NC}"; echo "$RESPONSE" | head -10; }

echo ""

# Test 4: A2A Protocol — check 3 artifacts in response
echo -e "${BLUE}Test 4: A2A Protocol - tasks/send (3-artifact response)${NC}"
A2A_RESPONSE=$(curl -s -X POST "$BASE_URL/a2a" \
    -H "Content-Type: application/json" \
    -d '{
        "jsonrpc": "2.0",
        "id": "test-001",
        "method": "tasks/send",
        "params": {
            "id": "task-demo-001",
            "messages": [
                {
                    "role": "user",
                    "parts": [{"type": "text", "text": "Full medication safety analysis please"}]
                }
            ],
            "metadata": {
                "sharp": {
                    "patient_id": "demo-001",
                    "fhir_server_url": "https://hapi.fhir.org/baseR4",
                    "user_role": "pharmacist"
                }
            }
        }
    }' --max-time 120)

echo "$A2A_RESPONSE" | python3 -c "
import sys, json
r = json.load(sys.stdin)
result = r.get('result', {})
print(f\"  Task ID: {result.get('id')}\")
print(f\"  Status: {result.get('status')}\")
artifacts = result.get('artifacts', [])
print(f\"  Artifacts: {len(artifacts)} (expected 3)\")
for a in artifacts:
    print(f\"    - {a['name']}: {a['description'][:60]}\")
meta = result.get('metadata', {}).get('medharmony', {})
if meta:
    print(f\"  Critical: {meta.get('critical_issues', 0)} | High: {meta.get('high_issues', 0)}\")
    print(f\"  Trace Steps: {meta.get('reasoning_trace_steps', 'N/A')}\")
" 2>/dev/null || echo "$A2A_RESPONSE" | head -20

echo ""

# =============================================================================
# SECTION D: Deploy Check (optional)
# =============================================================================
if [[ "$RUN_DEPLOY_CHECK" == "true" ]]; then
    echo -e "${BLUE}━━━ Section D: Deploy Check ━━━${NC}"
    bash scripts/deploy_check.sh --skip-demo 2>&1 | tail -20
    echo ""
fi

echo -e "${GREEN}✅ All tests completed!${NC}"
echo ""
echo "Tip: Run with --integration to test against live HAPI FHIR server"
echo "Tip: Run with --deploy-check to validate deployment readiness"
