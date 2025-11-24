# Universal Tool Adapter - Quick Summary

## What It Does

Makes Claude Code tools (Read, Write, Edit, Bash, etc.) work with **ANY** Ollama model.

## The Problem

- Claude Code uses Anthropic's tool format
- Most Ollama models don't understand this format
- Result: Tools don't work → Claude Code can't read/edit files

## The Solution

**Universal Tool Adapter** - Automatically detects model capabilities and adapts:

### 3-Tier System

**Tier 1** (llama3.1, mistral): Full OpenAI support
- ✅ Translates Anthropic → OpenAI format
- ✅ Native function calling
- ✅ Fully autonomous

**Tier 2** (qwen2.5-coder:14b, deepseek-r1): Partial support
- ✅ Some native support
- ✅ Adds guided prompts
- ⚠️ May need explicit instructions

**Tier 3** (qwen2.5-coder:7b, most others): Prompt-based
- ✅ Works via comprehensive prompts
- ✅ Teaches model to use special format
- ⚠️ Requires explicit tool mentions

## Installation

Already integrated! Just enable in `.env`:

```bash
TOOL_ADAPTER_ENABLED=true
```

## Usage

```bash
# Start proxy
./start.sh

# Check model capabilities
curl http://localhost:8000/v1/tool_adapter/info | jq

# Use Claude Code normally - tools work!
source setup-claude.sh
claude "Read server.py and explain it"
```

## Configuration

```bash
# .env
TOOL_ADAPTER_ENABLED=true          # Enable adapter
TOOL_ADAPTER_GUIDED=true            # Add guidance prompts
TOOL_ADAPTER_FALLBACK=true          # Fallback to prompt-based
TOOL_ADAPTER_NL_DETECTION=false     # Detect from natural language
TOOL_ADAPTER_DEBUG=false            # Debug logging
```

## Testing

```bash
# Quick test
curl -X POST http://localhost:8000/v1/tool_adapter/test | jq

# Full integration tests
cd tests
python test_tool_adapter_integration.py
```

## Model Recommendations

| Use Case | Recommended Model | Tier | Tool Support |
|----------|------------------|------|--------------|
| Best tools | llama3.1:70b | 1 | Excellent |
| Balanced | deepseek-r1:14b | 2 | Good |
| Fast/small | qwen2.5-coder:14b | 2 | Good |
| Smallest | qwen2.5-coder:7b | 3 | Limited |

## Key Features

✅ **Automatic Detection** - Knows 15+ model families
✅ **Runtime Switching** - Change models without config changes
✅ **Multi-Format** - Parses 5+ tool response formats
✅ **Graceful Fallback** - Works with unknown models
✅ **Zero Config** - Defaults work great

## How It Works (Simple)

```
Claude Code sends tools in Anthropic format
         ↓
Tool Adapter detects your Ollama model
         ↓
Tier 1: Converts to OpenAI format
Tier 2: Adds guidance + converts
Tier 3: Teaches via comprehensive prompts
         ↓
Ollama processes with tools
         ↓
Tool Adapter parses response (multiple formats)
         ↓
Converts back to Anthropic format
         ↓
Claude Code executes tools locally
         ↓
Tools work! 🎉
```

## Files Created

```
tool_adapter/
├── __init__.py                 # Package init
├── model_database.json         # 15+ known models
├── model_capabilities.py       # Tier detection
├── format_translator.py        # Format conversions
├── prompt_generator.py         # Tier-specific prompts
├── response_parser.py          # Multi-format parsing
└── adapter.py                  # Main orchestration

tests/
└── test_tool_adapter_integration.py

Documentation:
├── TOOL_ADAPTER.md            # Full documentation
├── TOOL_ADAPTER_SUMMARY.md    # This file
└── REALITY_CHECK.md          # Problem explanation
```

## Quick Comparison

| Without Adapter | With Adapter |
|----------------|--------------|
| Tools don't work | ✅ Tools work |
| Manual copy/paste | ✅ Autonomous |
| Only conversations | ✅ Full Claude Code |
| Limited to Anthropic | ✅ Any Ollama model |

## Documentation

- **Full Guide**: [TOOL_ADAPTER.md](TOOL_ADAPTER.md)
- **Problem Explained**: [REALITY_CHECK.md](REALITY_CHECK.md)
- **Tool Details**: [TOOLS.md](TOOLS.md)

## Success Metrics

After implementation:
- ✅ Works with qwen2.5-coder:7b (Tier 3)
- ✅ Works with deepseek-r1:14b (Tier 2)
- ✅ Works with llama3.1 (Tier 1)
- ✅ Auto-detects model capabilities
- ✅ Graceful fallback
- ✅ Runtime model switching
- ✅ Zero-config defaults

## Next Steps

1. **Test your model**:
   ```bash
   curl -X POST http://localhost:8000/v1/tool_adapter/test | jq
   ```

2. **Try with Claude Code**:
   ```bash
   claude "Read the file README.md"
   ```

3. **Check logs** to see detection in action

4. **Switch models** by editing `.env` and restarting

5. **Read full docs** if you want to optimize or extend

Happy coding with universal tool support! 🚀
