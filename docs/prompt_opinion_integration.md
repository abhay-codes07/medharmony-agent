# Prompt Opinion Integration Guide — MedHarmony

This guide walks through registering MedHarmony on the Prompt Opinion platform,
from hosting to SHARP context handoff.

---

## Overview

Prompt Opinion discovers agents by fetching their **Agent Card** at
`/.well-known/agent.json`. Once registered, it routes medication reconciliation
tasks to MedHarmony using the **A2A protocol** with the **SHARP extension**
for patient context propagation.

---

## Step 1: Host MedHarmony

Choose one of:

### Option A — Render.com (recommended for demos)

```bash
# 1. Push to GitHub
git push origin main

# 2. Go to https://render.com/new → "Web Service"
# 3. Connect your GitHub repo: abhay-codes07/medharmony-agent
# 4. Render auto-detects render.yaml — one-click deploy
# 5. Set environment variable: GEMINI_API_KEY = <your-key>
```

Your agent will be live at: `https://medharmony-agent.onrender.com`

### Option B — Fly.io

```bash
# Install flyctl: https://fly.io/docs/getting-started/installing-flyctl/
fly auth login
fly launch --name medharmony-agent --region sea
fly secrets set GEMINI_API_KEY=<your-key>
fly deploy
```

### Option C — Railway

```bash
# Install railway CLI: npm install -g @railway/cli
railway login
railway init
railway up
railway variables set GEMINI_API_KEY=<your-key>
```

### Option D — Local with ngrok (for testing)

```bash
# 1. Start the agent
python -m src.agent.server &

# 2. Create a public tunnel
ngrok http 8000

# 3. Update your .env
A2A_AGENT_URL=https://<ngrok-subdomain>.ngrok.io
```

---

## Step 2: Verify Your Agent Card

Before registering on Prompt Opinion, confirm your Agent Card is correct:

```bash
curl https://your-deployed-url/.well-known/agent.json | python3 -m json.tool
```

Expected response structure:
```json
{
  "name": "MedHarmony",
  "url": "https://your-deployed-url",
  "version": "1.0.0",
  "skills": [...],
  "extensions": {
    "sharp": {
      "supportsPatientContext": true,
      "fhirVersion": "R4",
      "requiredFhirResources": ["Patient", "MedicationRequest", ...]
    }
  }
}
```

---

## Step 3: Register on Prompt Opinion

1. Log in to the Prompt Opinion platform
2. Navigate to **Agents → Register New Agent**
3. Enter your Agent Card URL:
   ```
   https://your-deployed-url/.well-known/agent.json
   ```
4. Prompt Opinion fetches and validates the card automatically
5. Confirm the 4 skills are detected:
   - `medication-reconciliation`
   - `drug-interaction-analysis`
   - `deprescribing-advisor`
   - `clinician-safety-brief`
6. Enable **SHARP patient context** in the integration settings

**Screenshots placeholder:**
> [ Screenshot: PO Agent Registration Form ]
> [ Screenshot: Skills confirmation screen ]

---

## Step 4: Configure SHARP Context Handoff

Prompt Opinion sends patient context to MedHarmony via the SHARP extension
in the A2A task metadata. MedHarmony reads it from two locations:

### Location 1 — Structured SHARP metadata (preferred)
```json
{
  "metadata": {
    "sharp": {
      "patient_id": "592750",
      "fhir_server_url": "https://hapi.fhir.org/baseR4",
      "fhir_access_token": "Bearer <token>",
      "encounter_id": "enc-001",
      "user_role": "pharmacist",
      "organization_id": "org-hospital-001"
    }
  }
}
```

### Location 2 — Flat metadata keys (fallback)
```json
{
  "metadata": {
    "patient_id": "592750",
    "fhir_server_url": "https://hapi.fhir.org/baseR4"
  }
}
```

### Location 3 — Inline in message text (last resort)
MedHarmony also parses `patient_id: <value>` from free-text user messages.

---

## Step 5: Test the Integration

Send a test task via the A2A protocol:

```bash
curl -X POST https://your-deployed-url/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "test-po-001",
    "method": "tasks/send",
    "params": {
      "id": "task-test-001",
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
          "fhir_server_url": "https://hapi.fhir.org/baseR4",
          "user_role": "pharmacist"
        }
      }
    }
  }'
```

Expected response includes 3 artifacts:
1. `clinician_safety_brief` — Formatted Markdown brief
2. `analysis_data` — Structured JSON (all findings)
3. `reasoning_trace` — Agent reasoning timeline

---

## Step 6: Check the Reasoning Trace

MedHarmony v1.0 (Week 3) exposes a full reasoning trace in every A2A response:

```json
{
  "artifacts": [
    { "name": "reasoning_trace", "parts": [{ "type": "data", "data": {
      "total_duration_ms": 4231,
      "step_count": 12,
      "entries": [
        { "step_type": "pipeline_step", "tool_name": "fhir_data_pull", ... },
        { "step_type": "tool_call", "tool_name": "check_drug_interactions", ... },
        ...
      ]
    }}]}
  ]
}
```

And in `metadata.medharmony.reasoning_trace_url` once hosted.

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | ✅ | Google Gemini API key |
| `A2A_AGENT_URL` | ✅ | Public URL of deployed agent |
| `FHIR_SERVER_URL` | optional | Default FHIR server (overridable per-request) |
| `A2A_HOST` | optional | Bind host (default: `0.0.0.0`) |
| `A2A_PORT` | optional | Bind port (default: `8000`; Render: `10000`) |
| `GEMINI_MODEL` | optional | Gemini model name (default: `gemini-2.0-flash`) |
| `LOG_LEVEL` | optional | `DEBUG`, `INFO`, `WARNING` (default: `INFO`) |

---

## Screenshots Placeholder (Week 4)

> TODO: Add screenshots in Week 4
> - [ ] Render deploy confirmation
> - [ ] Prompt Opinion agent registration
> - [ ] Running analysis in PO UI
> - [ ] Clinician brief output
