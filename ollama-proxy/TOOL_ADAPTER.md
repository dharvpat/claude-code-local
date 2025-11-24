# Universal Tool Adapter

The Universal Tool Adapter makes Claude Code's tools work with **any** Ollama model through intelligent adaptation and format translation.

## Problem It Solves

Claude Code uses Anthropic's tool calling format, but most Ollama models either:
- Don't understand this format at all
- Use different formats (OpenAI, custom, etc.)
- Have limited or no native function calling support

**Without the adapter**: Tools don't work, Claude Code can't read files, edit code, or run commands.

**With the adapter**: Tools work with ANY model through automatic format translation and guided prompts.

## How It Works

```
Claude Code Request (Anthropic Format)
         ↓
  [Tool Adapter Analyzes]
         ↓
   Detects Model Tier:
   - Tier 1: Full OpenAI support → Translate to OpenAI format
   - Tier 2: Partial support → Add guided prompts + translate
   - Tier 3: No support → Teach via comprehensive prompts
         ↓
   Sends Adapted Request to Ollama
         ↓
   Model Responds (various formats)
         ↓
  [Tool Adapter Parses Response]
         ↓
   Detects Tool Usage:
   - OpenAI function_call
   - XML-style tags (<tool></tool>)
   - TOOL:/INPUT: format
   - Natural language intent (optional)
         ↓
   Translates Back to Anthropic Format
         ↓
Claude Code Executes Tools Locally
```

## Model Tiers

### Tier 1: Native OpenAI Support
**Models**: llama3.1, llama3.2, mistral, mistral-large

**Capabilities**:
- Full native function calling
- Understands tool definitions
- Generates proper tool_use blocks

**Adapter Strategy**:
- Translate Anthropic → OpenAI format
- Minimal system prompt guidance
- Direct format conversion

**Example**:
```python
# Anthropic tools → OpenAI tools
{
  "name": "read_file",
  "description": "Read a file",
  "input_schema": {...}
}
→
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read a file",
    "parameters": {...}
  }
}
```

### Tier 2: Partial Support
**Models**: qwen2.5-coder:14b, qwen2.5-coder:32b, deepseek-r1, deepseek-coder

**Capabilities**:
- Some native function calling
- Benefits from guidance
- May use custom formats

**Adapter Strategy**:
- Try native format first
- Add guided system prompts
- Parse multiple response formats

**Guidance Example**:
```
TOOL USAGE INSTRUCTIONS:

You have access to the following tools:
• read_file: Read a file
  - file_path (string) [REQUIRED]

When you need to use a tool:
1. Identify which tool is appropriate
2. Call the tool with required parameters
3. Wait for the result before continuing
```

### Tier 3: Prompt-Based Only
**Models**: qwen2.5-coder:7b, phi3, gemma, codellama, and most others

**Capabilities**:
- No native function calling
- Can follow instructions
- Requires comprehensive teaching

**Adapter Strategy**:
- Don't send native tool definitions
- Inject comprehensive prompt-based instructions
- Parse various text-based tool formats

**Instructions Example**:
```
╔══════════════════════════════════════╗
║     TOOL USAGE INSTRUCTIONS          ║
╚══════════════════════════════════════╝

You MUST use these tools for file operations.

AVAILABLE TOOLS:
  read_file:
    Description: Read a file
    Parameters:
      • file_path (string) [REQUIRED]

HOW TO USE TOOLS:

<tool>tool_name</tool>
<input>{"parameter": "value"}</input>

EXAMPLE:
User: Read server.py
You: <tool>read_file</tool>
<input>{"file_path": "server.py"}</input>
```

## Configuration

### Enable/Disable Tool Adapter

```bash
# .env
TOOL_ADAPTER_ENABLED=true  # Enable adapter (default: true)
```

### Guided Mode

Controls how much guidance is added to system prompts:

```bash
TOOL_ADAPTER_GUIDED=true  # Add detailed instructions (default: true)
```

- **true**: Comprehensive instructions, higher success rate
- **false**: Minimal guidance, cleaner prompts

### Fallback Mode

Whether to fall back to prompt-based if native fails:

```bash
TOOL_ADAPTER_FALLBACK=true  # Enable fallback (default: true)
```

### Natural Language Detection

Detect tool usage from conversational text (proactive mode):

```bash
TOOL_ADAPTER_NL_DETECTION=false  # Disable by default
```

Example detected patterns:
- "I need to read the file server.py" → read_file tool
- "Let me run ls -la" → bash tool
- "I'll write to config.json" → write_file tool

**Caution**: May misinterpret, use sparingly.

### Debug Mode

Enable detailed logging:

```bash
TOOL_ADAPTER_DEBUG=false  # Disable by default
```

## Model Database

The adapter knows about 15+ model families in `tool_adapter/model_database.json`:

```json
{
  "models": {
    "llama3.1:*": {
      "tier": 1,
      "format": "openai",
      "supports_native_tools": true
    },
    "qwen2.5-coder:14b": {
      "tier": 2,
      "format": "qwen",
      "supports_native_tools": true
    },
    "qwen2.5-coder:7b": {
      "tier": 3,
      "format": "prompt-based",
      "supports_native_tools": false
    }
  }
}
```

### Adding Custom Models

Edit `model_database.json` or add at runtime:

```python
from tool_adapter import UniversalToolAdapter

adapter = UniversalToolAdapter("my-model")
adapter.capabilities.add_model(
    "my-custom-model:latest",
    tier=2,  # 1, 2, or 3
    format_type="openai",
    supports_native=True,
    notes="Custom model with OpenAI function calling"
)
```

## API Endpoints

### Get Tool Adapter Info

```bash
GET /v1/tool_adapter/info
```

Returns:
```json
{
  "enabled": true,
  "model": {
    "model": "qwen2.5-coder:7b",
    "tier": 3,
    "tier_name": "TIER_3_PROMPT_BASED",
    "format": "prompt-based",
    "supports_native_tools": false,
    "description": "No native tool support, using prompt-based approach"
  },
  "configuration": {
    "guided_mode": true,
    "fallback_enabled": true,
    "natural_language_detection": false,
    "debug": false
  }
}
```

### Test Tool Support

```bash
POST /v1/tool_adapter/test
```

Returns:
```json
{
  "model": "qwen2.5-coder:7b",
  "tier": 3,
  "supports_native": false,
  "format": "prompt-based",
  "would_use_native_tools": false,
  "system_prompt_length": 1250,
  "recommendation": "Limited tool support - using prompt-based approach. Consider upgrading to a better model for autonomous tool use."
}
```

## Usage Examples

### Check Current Model Capabilities

```bash
curl http://localhost:8000/v1/tool_adapter/info | jq
```

### Test with Different Models

```bash
# Edit .env
OLLAMA_MODEL=qwen2.5-coder:14b

# Restart proxy
./start.sh

# Test
curl -X POST http://localhost:8000/v1/tool_adapter/test | jq
```

### Use with Claude Code

```bash
# Start proxy with tool adapter enabled
./start.sh

# In another terminal
source setup-claude.sh

# Use normally - tools will work!
claude "Read server.py and explain the main function"
```

## Response Format Detection

The adapter can parse tool usage in multiple formats:

### Format 1: OpenAI function_call
```json
{
  "function_call": {
    "name": "read_file",
    "arguments": "{\"file_path\": \"server.py\"}"
  }
}
```

### Format 2: XML Tags (Prompt-Based)
```xml
<tool>read_file</tool>
<input>{"file_path": "server.py"}</input>
```

### Format 3: TOOL:/INPUT: Format
```
TOOL: read_file
INPUT: {"file_path": "server.py"}
```

### Format 4: Bracket Format
```
[TOOL: read_file]
[INPUT: {"file_path": "server.py"}]
```

### Format 5: JSON Function Format
```json
{
  "function": "read_file",
  "arguments": {"file_path": "server.py"}
}
```

All formats are automatically detected and converted to Anthropic's tool_use format.

## Performance Considerations

### Tier 1 Models (Best)
- ✅ Fast tool detection
- ✅ High accuracy
- ✅ Autonomous tool selection
- ⚠️  Larger models (higher RAM)

### Tier 2 Models (Good)
- ✅ Moderate performance
- ✅ Good with guidance
- ⚠️  May need explicit prompts
- ✅ Balanced size/capability

### Tier 3 Models (Limited)
- ⚠️  Slower tool detection
- ⚠️  Requires explicit instructions
- ⚠️  May not choose tools autonomously
- ✅ Smaller, faster inference

## Troubleshooting

### Tools Not Working

**Check tier**:
```bash
curl http://localhost:8000/v1/tool_adapter/info | jq '.model.tier'
```

**If Tier 3**: Model has no native support
- Tools will work but require explicit prompts
- Try: "Use the read_file tool to read server.py"
- Consider upgrading to Tier 1/2 model

**If Tier 1/2 but not working**:
- Enable debug: `TOOL_ADAPTER_DEBUG=true`
- Check logs for parsing errors
- Try fallback: `TOOL_ADAPTER_FALLBACK=true`

### Model Not Recognized

**Add to database**:
```bash
# Edit tool_adapter/model_database.json
{
  "my-model:*": {
    "tier": 2,
    "format": "openai",
    "supports_native_tools": true
  }
}
```

**Or use wildcard**: Unknown models default to Tier 3

### Response Parsing Fails

**Enable all parsers**:
```bash
TOOL_ADAPTER_FALLBACK=true
```

**Enable debug logging**:
```bash
TOOL_ADAPTER_DEBUG=true
```

**Check response format** in logs - may need custom parser

### Guided Prompts Too Long

**Disable guidance**:
```bash
TOOL_ADAPTER_GUIDED=false
```

**Trade-off**: Shorter prompts but lower success rate

## Best Practices

### 1. Choose the Right Model

For best tool support:
1. **First choice**: llama3.1:70b (if you have RAM)
2. **Good balance**: deepseek-r1:14b
3. **Smaller**: qwen2.5-coder:14b
4. **Fastest**: qwen2.5-coder:7b (limited tools)

### 2. Use Explicit Prompts with Tier 3

Instead of:
```
claude "Fix the bug in server.py"
```

Try:
```
claude "First read server.py, then identify and fix the bug"
```

### 3. Monitor Tool Detection

Check logs for:
```
Tool detected: read_file
Tool adapter prepared request: openai format
Parsed response: tool_use
```

### 4. Test Before Production

```bash
# Test current model
curl -X POST http://localhost:8000/v1/tool_adapter/test | jq

# Run integration tests
cd tests
python test_tool_adapter_integration.py
```

### 5. Adjust Configuration

Start conservative, enable features as needed:
```bash
# Start here
TOOL_ADAPTER_ENABLED=true
TOOL_ADAPTER_GUIDED=true
TOOL_ADAPTER_FALLBACK=true
TOOL_ADAPTER_NL_DETECTION=false
TOOL_ADAPTER_DEBUG=false

# If tools don't work, enable debug
TOOL_ADAPTER_DEBUG=true

# If still failing, try NL detection (carefully)
TOOL_ADAPTER_NL_DETECTION=true
```

## Architecture

### Components

1. **ModelCapabilities** - Detects model tier and format
2. **FormatTranslator** - Converts between formats
3. **PromptGenerator** - Creates tier-specific prompts
4. **ResponseParser** - Detects tool usage in responses
5. **UniversalToolAdapter** - Orchestrates everything

### Integration Points

The adapter hooks into the proxy at:
1. **Request preparation**: Adapts tools and system prompt
2. **Response parsing**: Detects and translates tool usage

### Data Flow

```
Request:
  Anthropic tools → Adapter.prepare_request()
  → Tier detection
  → Format translation
  → Prompt generation
  → Ollama-compatible request

Response:
  Ollama response → Adapter.parse_response()
  → Multi-format detection
  → Tool extraction
  → Anthropic tool_use format
  → Claude Code
```

## Extending the Adapter

### Add New Model Format

1. **Update database**:
```json
{
  "new-model:*": {
    "tier": 2,
    "format": "custom",
    "supports_native_tools": true
  }
}
```

2. **Add format translator**:
```python
# In format_translator.py
def anthropic_to_custom_tools(self, tools):
    # Your translation logic
    pass
```

3. **Add response parser**:
```python
# In response_parser.py
def _parse_custom_format(self, response):
    # Your parsing logic
    pass
```

### Add New Detection Pattern

```python
# In response_parser.py
def _try_alternative_formats(self, content):
    # Add your pattern
    pattern = r'MY_PATTERN'
    match = re.search(pattern, content)
    if match:
        # Extract and return tool_use dict
        pass
```

## Comparison with Native Anthropic

| Feature | Anthropic Claude | Tool Adapter + Ollama |
|---------|-----------------|----------------------|
| Tool Support | ✅ Native | ⚠️ Adapted (model-dependent) |
| Accuracy | ✅ Excellent | ⚠️ Good (Tier 1/2) to Limited (Tier 3) |
| Speed | ✅ Fast API | ⚠️ Local inference (slower) |
| Privacy | ❌ Cloud | ✅ Fully local |
| Cost | ❌ Per-token | ✅ Free (local) |
| Offline | ❌ No | ✅ Yes |
| Model Choice | ❌ Fixed | ✅ Any Ollama model |

## FAQ

**Q: Will tools work with qwen2.5-coder:7b?**
A: Yes, but with limitations. The model uses prompt-based tools (Tier 3), so it needs explicit instructions. Works but less autonomous than Tier 1/2 models.

**Q: Which model is best for tool support?**
A: llama3.1:70b (Tier 1) if you have RAM, otherwise deepseek-r1:14b or qwen2.5-coder:14b (Tier 2).

**Q: Can I switch models at runtime?**
A: Yes! Just edit `.env` and restart the proxy. The adapter automatically detects the new model's capabilities.

**Q: Do I need to configure anything?**
A: No - defaults work well. The adapter auto-detects model capabilities and adapts accordingly.

**Q: What if my model isn't in the database?**
A: It defaults to Tier 3 (prompt-based), which works with all models. Add it to the database for optimization.

**Q: Can I disable the adapter?**
A: Yes: `TOOL_ADAPTER_ENABLED=false`. But tools won't work with most models.

**Q: How do I know if tools are working?**
A: Enable debug (`TOOL_ADAPTER_DEBUG=true`) and watch logs, or test with simple file operations.

**Q: Will this work with future models?**
A: Yes - unknown models default to Tier 3. Add new models to the database as they're released.

## Support

For issues:
- Check tier: `GET /v1/tool_adapter/info`
- Test support: `POST /v1/tool_adapter/test`
- Enable debug: `TOOL_ADAPTER_DEBUG=true`
- Read logs in proxy output
- See [REALITY_CHECK.md](REALITY_CHECK.md) for detailed explanation

## Credits

Built to solve the tool compatibility challenge between Claude Code and Ollama models. Enables full offline, private Claude Code usage with any local LLM.
