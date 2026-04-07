# 🏥 MedHarmony Agent

### Intelligent Medication Reconciliation & Safety Agent for Healthcare

> **Built for the [Agents Assemble Hackathon](https://agents-assemble.devpost.com/) — Option 3: Custom A2A Agent**

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
┌─────────────────────┐               ┌──────────────────────────────────┐
│                     │   FHIR        │     MedHarmony A2A Agent         │
│  User ──► User      │   Context     │                                  │
│           Agent  ───┼──────────────►│  ┌─ Reconciliation Engine        │
│                     │  (SHARP)      │  ├─ Interaction Analyzer          │
│                     │               │  ├─ Deprescribing Advisor         │
└─────────────────────┘               │  └─ Clinician Brief Generator     │
                                      │                                  │
                                      │  LLM: Claude (Anthropic API)     │
                                      │                                  │
                                      │  MCP Servers:                    │
                                      │  ├─ FHIR Data Server             │
                                      │  ├─ Drug Interaction Server      │
                                      │  └─ Clinical Guidelines Server   │
                                      └──────────────────────────────────┘
```

---

## ✨ Features

| Feature | Description | Prompt Opinion 5T |
|---------|-------------|-------------------|
| **Medication Reconciliation** | Compares med lists across admission, discharge, outpatient | 📊 Table |
| **Interaction Analysis** | Drug-drug, drug-condition, drug-allergy checks | 💬 Talk |
| **Deprescribing Advisor** | Beers Criteria / STOPP-START guided recommendations | 📄 Template |
| **FHIR Write-back** | Updates reconciled medication list in EHR | 🔄 Transaction |
| **Follow-up Tasks** | Creates tasks for clinician review items | ✅ Task |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- [Anthropic API Key](https://console.anthropic.com/)
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
# Edit .env with your API keys
```

### Run the Agent

```bash
# Start MCP servers
python -m src.mcp_servers.fhir_server.server &
python -m src.mcp_servers.drug_interaction_server.server &
python -m src.mcp_servers.clinical_guidelines_server.server &

# Start the A2A agent
python -m src.agent.server

# Or use the convenience script
./scripts/start.sh
```

### Run with Docker

```bash
docker-compose up --build
```

---

## 📋 Judging Criteria Alignment

| Criteria | How MedHarmony Delivers |
|----------|------------------------|
| **The AI Factor** | Uses Claude for multi-step clinical reasoning over unstructured data — impossible with rule-based systems |
| **Potential Impact** | Targets medication errors ($177B/year cost), polypharmacy (40%+ elderly), and care transitions |
| **Feasibility** | Built on standard FHIR resources, open drug databases (RxNorm/OpenFDA), and published clinical guidelines |

---

## 🛠️ Tech Stack

- **Agent Protocol**: A2A (Agent-to-Agent) with SHARP context propagation
- **Tool Protocol**: MCP (Model Context Protocol)
- **LLM**: Claude (Anthropic API)
- **Healthcare Data**: HL7 FHIR R4
- **Drug Data**: RxNorm / OpenFDA
- **Clinical Guidelines**: Beers Criteria, STOPP/START v3
- **Synthetic Data**: Synthea patient generator
- **Language**: Python 3.11+
- **Framework**: FastAPI + Uvicorn
- **Platform**: Prompt Opinion Marketplace

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
│   │   ├── interactions.py     # Drug interaction analyzer
│   │   ├── deprescribing.py    # Deprescribing advisor
│   │   ├── brief_generator.py  # Clinician brief generator
│   │   └── llm_client.py       # Claude API wrapper
│   ├── mcp_servers/        # MCP tool servers
│   │   ├── fhir_server/    # FHIR data access
│   │   ├── drug_interaction_server/  # Drug interactions
│   │   └── clinical_guidelines_server/ # Guidelines RAG
│   ├── models/             # Data models
│   │   ├── medication.py
│   │   ├── patient.py
│   │   └── fhir_types.py
│   └── utils/              # Shared utilities
│       ├── fhir_client.py
│       ├── sharp_context.py
│       └── logging.py
├── tests/                  # Test suite
├── data/                   # Synthetic data & guidelines
├── scripts/                # Helper scripts
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

- [Prompt Opinion](https://www.promptopinion.ai/) for the platform and hackathon
- [Anthropic](https://www.anthropic.com/) for Claude API
- [HL7 FHIR](https://hl7.org/fhir/) for healthcare data standards
- [Synthea](https://synthetichealth.github.io/synthea/) for synthetic patient data
