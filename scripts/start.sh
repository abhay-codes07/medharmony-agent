#!/bin/bash
# =============================================================================
# MedHarmony Agent - Start Script
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}"
echo "  ╔══════════════════════════════════════════╗"
echo "  ║       🏥 MedHarmony Agent v1.0.0         ║"
echo "  ║  Medication Reconciliation & Safety       ║"
echo "  ╚══════════════════════════════════════════╝"
echo -e "${NC}"

# Check for .env
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  No .env file found. Copying from .env.example...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}   Please edit .env with your ANTHROPIC_API_KEY${NC}"
    echo ""
fi

# Check for virtual environment
if [ ! -d "venv" ]; then
    echo -e "${BLUE}Creating virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install deps
echo -e "${BLUE}Installing dependencies...${NC}"
pip install -q -r requirements.txt

echo ""
echo -e "${GREEN}Starting MedHarmony A2A Agent...${NC}"
echo -e "  Agent Card:  http://localhost:8000/.well-known/agent.json"
echo -e "  A2A Endpoint: http://localhost:8000/a2a"
echo -e "  Health:       http://localhost:8000/health"
echo -e "  Direct API:   http://localhost:8000/api/analyze"
echo ""

# Start the A2A agent server
python -m src.agent.server
