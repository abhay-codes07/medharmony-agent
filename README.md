# 🏥 MedHarmony Agent

### Intelligent Medication Reconciliation & Safety Agent for Healthcare

> Production-grade medication safety agent built on open healthcare standards (MCP, A2A, FHIR)

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

## 🏗️ Architecture

```
Prompt Opinion Workspace              MedHarmony Infrastructure
┌─────────────────────┐               ┌──────────────────────────────────────┐
│                     │   FHIR        │     MedHarmony A2A Agent             │
│  User ──► User      │   Context     │                                      │
│           Agent  ───┼──────────────►│  ┌─ Reconciliation Engine            │
│                     │  (SHARP)      │  ├─ Interaction Analyzer             │
│                     │               │  ├─ Deprescribing Advisor            │
└─────────────────────┘               │  └─ Clinician Brief Generator        │
                                      │                                      │
                                      │  LLM: Google Gemini 3.0 Flash        │
                                      │                                      │
                                      │  MCP Servers (agentic tool use):     │
                                      │  ├─ FHIR Data Server                 │
                                      │  ├─ Drug Interaction Server          │
                                      │  └─ Clinical Guidelines Server       │
                                      └──────────────────────────────────────┘
```

The agent uses Gemini's native function-calling to autonomously decide which MCP
tools to invoke, in what order, during each reasoning step — producing a fully
traceable agentic execution log.

---

## ✨ Features

| Feature | Description | Prompt Opinion 5T |
|---------|-------------|-------------------|
| **Medication Reconciliation** | Compares med lists across admission, discharge, outpatient | 📊 Table |
| **Interaction Analysis** | Drug-drug, drug-condition, drug-allergy checks via RxNorm | 💬 Talk |
| **Deprescribing Advisor** | Beers Criteria / STOPP-START guided recommendations | 📄 Template |
| **FHIR Write-back** | Updates reconciled medication list in EHR | 🔄 Transaction |
| **Follow-up Tasks** | Creates tasks for clinician review items | ✅ Task |
| **Agentic Tool Trace** | Full audit log of every MCP tool call and result | 🔍 Trace |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- [Google Gemini API Key](https://aistudio.google.com/apikey)
- [Prompt Opinion Account](https://app.promptopinion.ai)

### Installation

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/medharmony-agent.git
cd medharmony-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment config
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### Run the Agent

```bash
# Start the A2A agent (MCP servers are launched automatically by the bridge)
python -m src.agent.server

# Or use the convenience script
./scripts/start.sh

# Run the full demo (shows agentic tool-call trace)
./scripts/demo.sh
```

### Run with Docker

```bash
docker-compose up --build
```

---

## 🛠️ Tech Stack

- **Agent Protocol**: A2A (Agent-to-Agent) with SHARP context propagation
- **Tool Protocol**: MCP (Model Context Protocol)
- **LLM**: Google Gemini 3.0 Flash
- **Healthcare Data**: HL7 FHIR R4
- **Drug Data**: RxNorm / OpenFDA
- **Clinical Guidelines**: Beers Criteria 2023, STOPP/START v3
- **Synthetic Data**: Synthea patient generator
- **Language**: Python 3.11+
- **Framework**: FastAPI + Uvicorn
- **Platform**: Prompt Opinion Marketplace

---

## 🤖 Agentic Tool Use (Week 2)

MedHarmony's core reasoning loop uses Gemini's native function-calling to
autonomously orchestrate MCP tool calls. Watching the agent reason looks like:

```
[tool-loop] iteration=0  tool_calls=['get_patient_summary']
  → calling tool: get_patient_summary({'patient_id': 'demo-001'})
  ✓ get_patient_summary returned 2847 chars

[tool-loop] iteration=1  tool_calls=['check_drug_interactions']
  → calling tool: check_drug_interactions({'drug_list': ['warfarin', 'ibuprofen', 'apixaban']})
  ✓ check_drug_interactions returned 1203 chars

[tool-loop] iteration=2  tool_calls=['search_deprescribing_guidelines']
  → calling tool: search_deprescribing_guidelines({'medications': ['diazepam', 'diphenhydramine'], 'age': 78, 'egfr': 32.0})
  ✓ search_deprescribing_guidelines returned 984 chars

Gemini finished after 3 tool iterations; response length: 4091 chars
```

---

## 📁 Project Structure

```
medharmony-agent/
├── src/
│   ├── agent/              # A2A Agent implementation
│   │   ├── server.py       # FastAPI A2A server
│   │   ├── agent_card.py   # A2A Agent Card definition
│   │   ├── handler.py      # Message/task handler
│   │   └── config.py       # Agent configuration
│   ├── core/               # Business logic
│   │   ├── reconciliation.py   # Med reconciliation engine
│   │   ├── llm_client.py       # Gemini API wrapper + agentic loop
│   │   ├── mcp_tool_bridge.py  # MCP ↔ Gemini tool format bridge
│   │   └── agent_loop.py       # Centralized agentic reasoning loop
│   ├── mcp_servers/        # MCP tool servers
│   │   ├── fhir_server/    # FHIR data access (6 tools)
│   │   ├── drug_interaction_server/  # RxNorm interactions (3 tools)
│   │   └── clinical_guidelines_server/ # Beers/STOPP-START (3 tools)
│   ├── models/             # Pydantic data models
│   └── utils/              # Shared utilities
├── tests/                  # Test suite
├── data/                   # Synthetic data & guidelines
├── scripts/                # Helper scripts
│   ├── start.sh
│   ├── test.sh
│   └── demo.sh             # Agentic tool-trace demo
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## 📄 License

MIT License — See [LICENSE](LICENSE)

---

## 🙏 Acknowledgments

- [Prompt Opinion](https://www.promptopinion.ai/) for the healthcare AI assembly platform
- [Google DeepMind](https://deepmind.google/) for the Gemini API
- [HL7 FHIR](https://hl7.org/fhir/) for healthcare data standards
- [Synthea](https://synthetichealth.github.io/synthea/) for synthetic patient data
- [Model Context Protocol](https://modelcontextprotocol.io/) for the tool integration standard
