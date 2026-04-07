#!/bin/bash
# =============================================================================
# MedHarmony Agent - Test Script
# Tests the A2A endpoint with a demo patient
# =============================================================================

set -e

BASE_URL="${1:-http://localhost:8000}"

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🧪 Testing MedHarmony Agent at ${BASE_URL}${NC}"
echo ""

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
print(f\"  Skills: {len(card['skills'])}\")
for s in card['skills']:
    print(f\"    - {s['name']}: {s['description'][:60]}...\")
print(f\"  SHARP Patient Context: {card['extensions']['sharp']['supportsPatientContext']}\")
"
echo ""

# Test 3: Direct API (demo patient)
echo -e "${BLUE}Test 3: Direct Analysis API (Demo Patient)${NC}"
echo "  Sending analysis request for demo patient Margaret Thompson (78F, 12 meds, CKD3b)..."
echo ""

RESPONSE=$(curl -s -X POST "$BASE_URL/api/analyze" \
    -H "Content-Type: application/json" \
    -d '{"patient_id": "demo-001"}')

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
print()
if r['tasks']:
    print('  Follow-up Tasks:')
    for t in r['tasks'][:5]:
        print(f'    • {t}')
" 2>/dev/null || echo -e "${RED}  Failed to parse response. Raw output:${NC}" && echo "$RESPONSE" | head -20

echo ""

# Test 4: A2A Protocol
echo -e "${BLUE}Test 4: A2A Protocol - tasks/send${NC}"
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
                    "parts": [
                        {
                            "type": "text",
                            "text": "Perform a full medication safety analysis for this patient"
                        }
                    ]
                }
            ],
            "metadata": {
                "sharp": {
                    "patient_id": "demo-001",
                    "fhir_server_url": "https://hapi.fhir.org/baseR4"
                }
            }
        }
    }')

echo "$A2A_RESPONSE" | python3 -c "
import sys, json
r = json.load(sys.stdin)
result = r.get('result', {})
print(f\"  Task ID: {result.get('id')}\")
print(f\"  Status: {result.get('status')}\")
artifacts = result.get('artifacts', [])
print(f\"  Artifacts: {len(artifacts)}\")
for a in artifacts:
    print(f\"    - {a['name']}: {a['description']}\")
meta = result.get('metadata', {}).get('medharmony', {})
if meta:
    print(f\"  Critical: {meta.get('critical_issues', 0)} | High: {meta.get('high_issues', 0)} | Moderate: {meta.get('moderate_issues', 0)}\")
" 2>/dev/null || echo "$A2A_RESPONSE" | head -20

echo ""
echo -e "${GREEN}✅ All tests completed!${NC}"
