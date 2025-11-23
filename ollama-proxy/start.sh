#!/bin/bash

# Ollama API Proxy Startup Script
# This script checks prerequisites and starts the proxy server

set -e  # Exit on error

echo "======================================"
echo "Ollama API Proxy for Claude Code"
echo "======================================"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
    echo -e "${GREEN}✓${NC} Loaded environment variables from .env"
else
    echo -e "${RED}✗${NC} .env file not found!"
    exit 1
fi

# Set defaults if not in .env
OLLAMA_ENDPOINT=${OLLAMA_ENDPOINT:-http://localhost:11434}
OLLAMA_MODEL=${OLLAMA_MODEL:-qwen2.5-coder:7b}
PROXY_PORT=${PROXY_PORT:-8000}

# Check if Ollama is running
echo ""
echo "Checking prerequisites..."
echo ""

if ! command -v ollama &> /dev/null; then
    echo -e "${RED}✗${NC} Ollama is not installed!"
    echo "Please install Ollama from https://ollama.ai"
    exit 1
fi
echo -e "${GREEN}✓${NC} Ollama is installed"

# Check if Ollama service is running
if ! curl -s "$OLLAMA_ENDPOINT/api/tags" > /dev/null 2>&1; then
    echo -e "${RED}✗${NC} Ollama service is not running at $OLLAMA_ENDPOINT"
    echo "Please start Ollama with: ollama serve"
    exit 1
fi
echo -e "${GREEN}✓${NC} Ollama service is running"

# Check if the model is available
echo ""
echo "Checking if model '$OLLAMA_MODEL' is available..."
if ! curl -s "$OLLAMA_ENDPOINT/api/tags" | grep -q "\"name\":\"$OLLAMA_MODEL\""; then
    echo -e "${YELLOW}⚠${NC}  Model '$OLLAMA_MODEL' not found"
    echo "Pulling model... (this may take a while)"
    ollama pull "$OLLAMA_MODEL"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} Model pulled successfully"
    else
        echo -e "${RED}✗${NC} Failed to pull model"
        exit 1
    fi
else
    echo -e "${GREEN}✓${NC} Model '$OLLAMA_MODEL' is available"
fi

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗${NC} Python 3 is not installed!"
    exit 1
fi
echo -e "${GREEN}✓${NC} Python 3 is installed"

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating Python virtual environment..."
    python3 -m venv venv
    echo -e "${GREEN}✓${NC} Virtual environment created"
fi

# Activate virtual environment
source venv/bin/activate
echo -e "${GREEN}✓${NC} Virtual environment activated"

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo -e "${GREEN}✓${NC} Dependencies installed"

# Check if port is available
if lsof -Pi :$PROXY_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${YELLOW}⚠${NC}  Port $PROXY_PORT is already in use"
    echo "Please stop the other process or change PROXY_PORT in .env"
    exit 1
fi
echo -e "${GREEN}✓${NC} Port $PROXY_PORT is available"

# Start the proxy server
echo ""
echo "======================================"
echo "Starting Ollama API Proxy"
echo "======================================"
echo ""
echo "Configuration:"
echo "  Ollama Endpoint: $OLLAMA_ENDPOINT"
echo "  Ollama Model: $OLLAMA_MODEL"
echo "  Proxy Port: $PROXY_PORT"
echo ""
echo "To use with Claude Code, run:"
echo "  source setup-claude.sh"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""
echo "======================================"
echo ""

# Start the server
python3 server.py
