# 🏥 MedHarmony Agent

### Intelligent Medication Reconciliation & Safety Agent for Healthcare

> Production-grade medication safety agent built on open healthcare standards (MCP, A2A, FHIR)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/abhay-codes07/medharmony-agent)

MedHarmony is an AI-powered A2A (Agent-to-Agent) agent that performs **intelligent medication reconciliation** across care transitions. It identifies dangerous drug interactions, flags contraindications based on patient-specific lab values, suggests evidence-based deprescribing opportunities, and generates clinician-ready safety briefs — all grounded in real FHIR patient data.

---

## 🧠 The Problem

**Medication errors are the #1 cause of preventable patient harm worldwide.**

- 1.5M+ adverse drug events per year in the US alone
- 40%+ of elderly patients are on 5+ medications (polypharmacy)
- Every care transition (admission → discharge → specialist) fragments medication lists
- Rule-based systems can't reason over unstructured notes, patient-specific physiology, and clinical guidelines simultaneously

**MedHarmony solves this with Generative AI grounded in FHIR data and clinical evidence.**

---

## 📄 Sample Clinician Brief

> **See [`docs/sample_brief.md`](docs/sample_brief.md) for a full rendered example.**

```markdown
# MedHarmony Clinician Safety Brief

Patient: Margaret Thompson | Age: 78 | Female | Weight: 62.0 kg | eGFR: 32.0 mL/min/1.73m²
Key Allergies: Penicillin, Sulfonamides

## 🚨 Critical Alerts
> ⚠️ Immediate clinician review required before discharge.

- Warfarin + Apixaban (Duplicate Therapy): Two anticoagulants simultaneously active.
  Action: Confirm anticoagulation strategy — for clinician review.
  Evidence: ACC/AHA Afib Guidelines 2023

- Ibuprofen + CKD Stage 3b: NSAIDs contraindicated at eGFR <45.
  Action: Discontinue ibuprofen, substitute acetaminophen — for clinician review.
  Evidence: KDIGO 2023; Beers Criteria 2023

## 📋 Medication Reconciliation Summary
| Medication     | Admission     | Discharge     | Action       | Reason                    |
|----------------|---------------|---------------|--------------|---------------------------|
| Metformin      | 1000 mg BID   | 500 mg BID    | ✏️ MODIFY    | CKD dose reduction        |
| Ibuprofen      | 400 mg TID    | —             | 🛑 DISCONTINUE | NSAID in CKD + anticoag |
| Apixaban       | —             | 5 mg BID      | 🔍 REVIEW    | Duplicate anticoagulation |
...

📊 14 medications | 3 critical | 2 high | 3 moderate | 3 deprescribing candidates
```

*[Screenshot placeholder — Week 4 will add visual screenshots of the rendered brief]*

---

## 🏗️ Architecture

```
Prompt Opinion Workspace              MedHarmony Infrastructure
┌─────────────────────┐               ┌──────────────────────────────────────────────┐
│                     │   FHIR        │     MedHarmony A2A Agent (Week 3)            │
│  User ──► User      │   Context     │                                              │
│           Agent  ───┼──────────────►│  ┌─ Reconciliation Engine                    │
│                     │  (SHARP)      │  ├─ Interaction Analyzer (MCP tools)         │
│                     │               │  ├─ Deprescribing Advisor (Beers/STOPP)      │
└─────────────────────┘               │  ├─ Jinja2 Brief Renderer                   │
                                      │  ├─ ReasoningTracer (observability)          │
                                      │  ├─ SafetyGuards (clinical validation)       │
                                      │  └─ AuditLog (HIPAA-style)                  │
                                      │                                              │
                                      │  LLM: Google Gemini (Flash)                 │
                                      │                                              │
                                      │  MCP Servers (agentic tool use):            │
                                      │  ├─ FHIR Data Server                        │
                                      │  ├─ Drug Interaction Server (RxNorm/FDA)    │
                                      │  └─ Clinical Guidelines Server              │
                                      └──────────────────────────────────────────────┘
```

---

## ✨ Features

| Feature | Description | Week |
|---------|-------------|------|
| **Medication Reconciliation** | Compares med lists across admission, discharge, outpatient | 1 |
| **Interaction Analysis** | Drug-drug, drug-condition, drug-allergy, drug-lab checks | 1 |
| **Deprescribing Advisor** | Beers Criteria 2023 / STOPP-START v3 guided recommendations | 1 |
| **MCP Agentic Tool Use** | Gemini autonomously calls FHIR, RxNorm, guideline tools | 2 |
| **Real FHIR Data** | Loads live patients from public HAPI FHIR test server | 3 |
| **Reasoning Trace** | Full observability: every LLM call, tool call, pipeline step | 3 |
| **Jinja2 Brief Template** | Deterministic, professional clinician brief formatting | 3 |
| **Safety Guards** | Clinical validation before output: framing, citations, severity | 3 |
| **HIPAA Audit Log** | JSON audit log for every patient data access | 3 |
| **Deploy to Render** | One-click deployment with render.yaml | 3 |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- [Google Gemini API Key](https://aistudio.google.com/apikey)

### Installation

```bash
git clone https://github.com/abhay-codes07/medharmony-agent.git
cd medharmony-agent

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### Run the Agent

```bash
# Start the A2A agent
python -m src.agent.server

# Run unit tests
pytest tests/ -v --ignore=tests/test_real_fhir.py

# Run the full test suite (live API tests)
bash scripts/test.sh

# Seed demo patients from HAPI FHIR
python scripts/seed_demo_data.py

# Pre-deployment validation
bash scripts/deploy_check.sh
```

### Quick Demo (no setup required)

```bash
# Start server
python -m src.agent.server &

# Analyze the built-in demo patient (Margaret Thompson, 78F, 12 meds, CKD3b)
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"patient_id": "demo-001"}'
```

### Docker

```bash
docker-compose up --build
```

---

## 🔍 Reasoning Trace (Week 3)

Every A2A response now includes a full reasoning trace as Artifact 3:

```json
{
  "name": "reasoning_trace",
  "data": {
    "total_duration_ms": 4231,
    "step_count": 12,
    "entries": [
      {"step_type": "pipeline_step", "tool_name": "fhir_data_pull",
       "result_summary": "loaded Margaret Thompson — 23 meds", "duration_ms": 142},
      {"step_type": "tool_call", "tool_name": "check_drug_interactions",
       "arguments": {"drug_list": ["warfarin", "ibuprofen", "apixaban"]}},
      {"step_type": "tool_result", "tool_name": "check_drug_interactions",
       "result_summary": "Found warfarin+NSAID interaction...", "duration_ms": 891},
      ...
    ]
  }
}
```

---

## 🏥 Real FHIR Data (Week 3)

MedHarmony now loads real patients from the public HAPI FHIR test server:

```bash
# Use a known demo patient from HAPI FHIR
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"patient_id": "592750", "fhir_server_url": "https://hapi.fhir.org/baseR4"}'

# Load your own Synthea patients
python scripts/seed_demo_data.py

# See data/synthetic_patients/README.md for Synthea setup instructions
```

Demo patient IDs (from `data/synthetic_patients/sample_patient_ids.json`):
- `demo-001` — Margaret Thompson (offline, always works)
- `592750` — Eleanor Vance (HAPI FHIR, Afib + CKD + warfarin/NSAID)
- `2744` — Harold Benson (HAPI FHIR, CHF + CKD + gout)

---

## 🚢 Deploy to Render

```bash
# 1. Push to GitHub
git push origin main

# 2. Click the button above, or:
#    - Go to https://render.com/new
#    - Connect repo: abhay-codes07/medharmony-agent
#    - Set GEMINI_API_KEY in the environment section
#    - render.yaml handles the rest automatically
```

See [`docs/prompt_opinion_integration.md`](docs/prompt_opinion_integration.md) for full Prompt Opinion setup.

---

## 📁 Project Structure

```
medharmony-agent/
├── src/
│   ├── agent/              # A2A Agent implementation
│   │   ├── server.py       # FastAPI A2A server
│   │   ├── agent_card.py   # A2A Agent Card (with SHARP, iconUrl, documentationUrl)
│   │   ├── handler.py      # Task handler (3 artifacts: brief + data + trace)
│   │   └── config.py       # Agent configuration
│   ├── core/               # Business logic
│   │   ├── reconciliation.py    # Main pipeline (FHIR → LLM → brief)
│   │   ├── llm_client.py        # Gemini API wrapper
│   │   ├── mcp_tool_bridge.py   # MCP ↔ Gemini tool bridge
│   │   ├── agent_loop.py        # Agentic reasoning loop + tracer integration
│   │   ├── brief_templates.py   # Jinja2 brief renderer (Week 3)
│   │   └── safety_guards.py     # Clinical output validation (Week 3)
│   ├── mcp_servers/        # MCP tool servers (3 servers, 12 tools)
│   ├── models/             # Pydantic data models (medication.py)
│   └── utils/
│       ├── fhir_client.py       # FHIR R4 async client
│       ├── sharp_context.py     # SHARP context extraction
│       ├── observability.py     # ReasoningTracer (Week 3)
│       └── audit_log.py         # HIPAA audit logging (Week 3)
├── data/
│   ├── templates/
│   │   └── clinician_brief.md.j2   # Jinja2 brief template (Week 3)
│   └── synthetic_patients/
│       ├── README.md               # Synthea setup instructions
│       └── sample_patient_ids.json # Known-good demo patients
├── docs/
│   ├── sample_brief.md             # Static example of rendered brief (Week 3)
│   └── prompt_opinion_integration.md  # PO registration guide (Week 3)
├── tests/
│   ├── test_core.py               # Core unit tests (Week 1-2)
│   ├── test_safety_guards.py      # Safety guard tests (Week 3)
│   ├── test_brief_template.py     # Template rendering tests (Week 3)
│   └── test_real_fhir.py          # Integration tests (Week 3, marked)
├── scripts/
│   ├── load_synthea_patients.py   # Upload Synthea bundles to FHIR (Week 3)
│   ├── seed_demo_data.py          # One-command demo data setup (Week 3)
│   ├── deploy_check.sh            # Pre-deployment validation (Week 3)
│   └── test.sh                    # Test runner (updated Week 3)
├── Procfile                       # Render/Heroku deployment (Week 3)
├── render.yaml                    # Render.com blueprint (Week 3)
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## 🛠️ Tech Stack

- **Agent Protocol**: A2A (Agent-to-Agent) with SHARP context propagation
- **Tool Protocol**: MCP (Model Context Protocol)
- **LLM**: Google Gemini Flash
- **Healthcare Data**: HL7 FHIR R4 (HAPI FHIR public test server)
- **Drug Data**: RxNorm / OpenFDA
- **Clinical Guidelines**: Beers Criteria 2023, STOPP/START v3
- **Synthetic Data**: Synthea patient generator
- **Brief Templates**: Jinja2
- **Language**: Python 3.11+
- **Framework**: FastAPI + Uvicorn
- **Platform**: Prompt Opinion Marketplace

---

## 📄 License

MIT License — See [LICENSE](LICENSE)
