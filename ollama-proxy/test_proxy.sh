#!/bin/bash

# Test script for Ollama API Proxy
# This script tests the proxy endpoints

set -e

PROXY_URL="http://localhost:8000"

echo "======================================"
echo "Ollama API Proxy Tests"
echo "======================================"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Test 1: Health check
echo "Test 1: Health check (GET /)"
response=$(curl -s "$PROXY_URL/" | jq -r '.status' 2>/dev/null || echo "error")
if [ "$response" = "ok" ]; then
    echo -e "${GREEN}✓${NC} Health check passed"
else
    echo -e "${RED}✗${NC} Health check failed"
    exit 1
fi
echo ""

# Test 2: List models
echo "Test 2: List models (GET /v1/models)"
response=$(curl -s "$PROXY_URL/v1/models" | jq -r '.data[0].id' 2>/dev/null || echo "error")
if [ "$response" != "error" ] && [ -n "$response" ]; then
    echo -e "${GREEN}✓${NC} List models passed (found: $response)"
else
    echo -e "${RED}✗${NC} List models failed"
    exit 1
fi
echo ""

# Test 3: Simple message
echo "Test 3: Simple message (POST /v1/messages)"
response=$(curl -s -X POST "$PROXY_URL/v1/messages" \
  -H "Content-Type: application/json" \
  -H "x-api-key: test" \
  -d '{
    "model": "claude-3-opus-20240229",
    "messages": [{"role": "user", "content": "Say just the word: HELLO"}],
    "max_tokens": 10
  }' | jq -r '.content[0].text' 2>/dev/null || echo "error")

if [ "$response" != "error" ] && [ -n "$response" ]; then
    echo -e "${GREEN}✓${NC} Simple message passed"
    echo "   Response: $response"
else
    echo -e "${RED}✗${NC} Simple message failed"
    echo "   Response: $response"
    exit 1
fi
echo ""

# Test 4: Token counting
echo "Test 4: Token counting (POST /v1/messages/count_tokens)"
response=$(curl -s -X POST "$PROXY_URL/v1/messages/count_tokens" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello, world!"}]
  }' | jq -r '.input_tokens' 2>/dev/null || echo "error")

if [ "$response" != "error" ] && [ "$response" -gt 0 ]; then
    echo -e "${GREEN}✓${NC} Token counting passed (estimated: $response tokens)"
else
    echo -e "${RED}✗${NC} Token counting failed"
    exit 1
fi
echo ""

# Test 5: Multi-turn conversation
echo "Test 5: Multi-turn conversation (POST /v1/messages)"
response=$(curl -s -X POST "$PROXY_URL/v1/messages" \
  -H "Content-Type: application/json" \
  -H "x-api-key: test" \
  -d '{
    "model": "claude-3-opus-20240229",
    "messages": [
      {"role": "user", "content": "What is 2+2?"},
      {"role": "assistant", "content": "4"},
      {"role": "user", "content": "What is 3+3?"}
    ],
    "max_tokens": 10
  }' | jq -r '.role' 2>/dev/null || echo "error")

if [ "$response" = "assistant" ]; then
    echo -e "${GREEN}✓${NC} Multi-turn conversation passed"
else
    echo -e "${RED}✗${NC} Multi-turn conversation failed"
    exit 1
fi
echo ""

echo "======================================"
echo -e "${GREEN}All tests passed!${NC}"
echo "======================================"
echo ""
echo "The proxy is working correctly."
echo "You can now use it with Claude Code by running:"
echo "  source setup-claude.sh"
echo ""
