"""MedHarmony Agent Configuration."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
GUIDELINES_DIR = DATA_DIR / "guidelines"
SYNTHETIC_PATIENTS_DIR = DATA_DIR / "synthetic_patients"

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

# A2A Agent
A2A_HOST = os.getenv("A2A_HOST", "0.0.0.0")
A2A_PORT = int(os.getenv("A2A_PORT", "8000"))
A2A_AGENT_NAME = os.getenv("A2A_AGENT_NAME", "MedHarmony")
A2A_AGENT_URL = os.getenv("A2A_AGENT_URL", "http://localhost:8000")

# MCP Servers
FHIR_MCP_PORT = int(os.getenv("FHIR_MCP_PORT", "8001"))
DRUG_MCP_PORT = int(os.getenv("DRUG_MCP_PORT", "8002"))
GUIDELINES_MCP_PORT = int(os.getenv("GUIDELINES_MCP_PORT", "8003"))

# FHIR
FHIR_SERVER_URL = os.getenv("FHIR_SERVER_URL", "https://hapi.fhir.org/baseR4")
FHIR_AUTH_TOKEN = os.getenv("FHIR_AUTH_TOKEN", "")

# Drug APIs
OPENFDA_API_KEY = os.getenv("OPENFDA_API_KEY", "")
RXNORM_API_URL = os.getenv("RXNORM_API_URL", "https://rxnav.nlm.nih.gov/REST")

# Prompt Opinion
PO_PLATFORM_URL = os.getenv("PO_PLATFORM_URL", "https://app.promptopinion.ai")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
