#!/bin/bash

# Claude Code Environment Setup for Ollama Proxy
# Source this file to configure Claude Code to use the Ollama proxy
# Usage: source setup-claude.sh

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment variables from .env
if [ -f "$SCRIPT_DIR/.env" ]; then
    source <(grep -v '^#' "$SCRIPT_DIR/.env" | sed 's/^/export /')
else
    echo "Error: .env file not found in $SCRIPT_DIR"
    return 1
fi

# Set defaults
PROXY_PORT=${PROXY_PORT:-8000}

# Configure Claude Code to use the Ollama proxy
export ANTHROPIC_BASE_URL="http://localhost:$PROXY_PORT"
export ANTHROPIC_API_KEY="ollama-proxy-dummy-key"

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "======================================"
echo "Claude Code → Ollama Proxy Setup"
echo "======================================"
echo ""
echo -e "${GREEN}✓${NC} Environment configured for Ollama proxy"
echo ""
echo "Configuration:"
echo "  ANTHROPIC_BASE_URL=$ANTHROPIC_BASE_URL"
echo "  ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY"
echo ""
echo -e "${YELLOW}Note:${NC} Make sure the proxy server is running!"
echo "      Start it with: cd $SCRIPT_DIR && ./start.sh"
echo ""
echo "You can now use Claude Code normally, and all requests"
echo "will be forwarded to your local Ollama instance."
echo ""
echo "To test, try:"
echo "  claude --version"
echo "  claude 'Hello, how are you?'"
echo ""
echo "======================================"
echo ""
