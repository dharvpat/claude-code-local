# Ollama API Proxy for Claude Code

This proxy adapter allows Claude Code to work with Ollama's API locally, enabling you to run completely offline without sending data to the cloud.

## Overview

Claude Code is designed to work with Anthropic's API. This proxy server:
1. Accepts requests in Anthropic API format (which Claude Code uses)
2. Translates them to Ollama API format
3. Forwards to your local Ollama instance
4. Translates responses back to Anthropic format
5. Returns to Claude Code

```
Claude Code → Anthropic API Format → Proxy → Ollama API Format → Ollama (localhost:11434)
                                       ↓
Claude Code ← Anthropic API Format ← Proxy ← Ollama Response
```

## Key Features

✅ **Full API Translation** - Anthropic ↔ Ollama format conversion
✅ **Tool Support** - Claude Code tools (Read, Write, Edit, Bash) work seamlessly
✅ **Context Caching** - Persistent sessions with 100K+ token support
✅ **Smart Retrieval** - Automatically loads relevant past context
✅ **Complete Privacy** - All data stays on your machine

## Prerequisites

1. **Ollama** - Install from [https://ollama.ai](https://ollama.ai)
2. **Python 3.8+** - For running the proxy server
3. **Claude Code** - Already installed on your system
4. **Ollama Model** - qwen2.5-coder:7b (or any other model you prefer)

## Installation

### 1. Install and Start Ollama

```bash
# Install Ollama (if not already installed)
# Visit https://ollama.ai for installation instructions

# Start Ollama service
ollama serve

# In another terminal, pull the model
ollama pull qwen2.5-coder:7b
```

### 2. Set Up the Proxy

```bash
# Navigate to the proxy directory
cd ollama-proxy

# Install Python dependencies (creates virtual environment automatically)
./start.sh
```

The `start.sh` script will:
- Check if Ollama is running
- Verify the model is available (pull if needed)
- Create a Python virtual environment
- Install dependencies
- Start the proxy server

## Configuration

Edit the `.env` file to customize settings:

```bash
# Ollama Configuration
OLLAMA_MODEL=qwen2.5-coder:7b          # Model to use
OLLAMA_ENDPOINT=http://localhost:11434  # Ollama endpoint
PROXY_PORT=8000                         # Proxy server port

# Anthropic API Version (for compatibility)
ANTHROPIC_API_VERSION=2023-06-01

# Optional: Enable debug logging
DEBUG=false
```

## Usage

### Step 1: Start the Proxy Server

In one terminal:

```bash
cd ollama-proxy
./start.sh
```

You should see output like:
```
======================================
Ollama API Proxy for Claude Code
======================================

✓ Loaded environment variables from .env
✓ Ollama is installed
✓ Ollama service is running
✓ Model 'qwen2.5-coder:7b' is available
✓ Python 3 is installed
✓ Virtual environment activated
✓ Dependencies installed
✓ Port 8000 is available

======================================
Starting Ollama API Proxy
======================================

Configuration:
  Ollama Endpoint: http://localhost:11434
  Ollama Model: qwen2.5-coder:7b
  Proxy Port: 8000

To use with Claude Code, run:
  source setup-claude.sh

Press Ctrl+C to stop the server
======================================

INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 2: Configure Claude Code

In another terminal:

```bash
cd ollama-proxy
source setup-claude.sh
```

This sets the environment variables:
- `ANTHROPIC_BASE_URL=http://localhost:8000`
- `ANTHROPIC_API_KEY=ollama-proxy-dummy-key`

### Step 3: Use Claude Code Normally

Now you can use Claude Code as usual, and all requests will go through your local Ollama instance:

```bash
# Test with a simple query
claude "What is 2+2?"

# Interactive mode
claude

# Run on files
claude "Explain this code" file.py
```

## How It Works

### API Translation

The proxy translates between two different API formats:

#### Request Translation (Anthropic → Ollama)

**Anthropic format:**
```json
{
  "model": "claude-3-opus-20240229",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "max_tokens": 1024,
  "temperature": 0.7
}
```

**Ollama format:**
```json
{
  "model": "qwen2.5-coder:7b",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "stream": false,
  "options": {
    "temperature": 0.7,
    "num_predict": 1024
  }
}
```

#### Response Translation (Ollama → Anthropic)

The proxy also translates responses, including:
- Message content and role
- Token usage statistics
- Stop reasons
- Tool calls (if supported by model)

### Endpoints Supported

| Endpoint | Status | Description |
|----------|--------|-------------|
| `GET /` | ✓ | Health check |
| `GET /v1/models` | ✓ | List available models |
| `POST /v1/messages` | ✓ | Create message (main endpoint) |
| `POST /v1/messages/count_tokens` | ✓ | Estimate token count |
| Other `/v1/*` | ⚠ | Returns 501 Not Implemented |

## Features & Limitations

### Supported Features

- ✓ Basic chat completion
- ✓ Multi-turn conversations
- ✓ System prompts
- ✓ Temperature and top_p control
- ✓ Max tokens configuration
- ✓ Token counting (estimated)
- ✓ Model listing
- ✓ **Context caching** - Persistent sessions with 100K+ token support (see [CACHING.md](CACHING.md))
- ✓ **Tool execution** - All Claude Code tools work (Read, Write, Edit, Bash, etc.) (see [TOOLS.md](TOOLS.md))

### Limitations

- ⚠ **Tool/Function Calling**: Limited by Ollama model capabilities
  - qwen2.5-coder:7b has limited function calling support
  - Tool calls are converted to text descriptions if not natively supported
  - **Note**: Tools ARE executed client-side and WILL work! See [TOOLS.md](TOOLS.md) for details
  - For better tool support, use models like deepseek-r1:14b or qwen2.5-coder:14b

- ⚠ **Multi-modal (Images)**: Limited by model support
  - qwen2.5-coder:7b does not support vision
  - Images are noted in the prompt but not processed
  - Consider using a vision-capable Ollama model for image support

- ⚠ **Context Caching**: Not supported
  - Anthropic's prompt caching feature is not available in Ollama
  - All prompts are processed from scratch each time

- ⚠ **Streaming**: Currently disabled
  - Responses are buffered and returned complete
  - This was chosen for simplicity (as per your preference)
  - Can be enabled in future versions

- ⚠ **Performance**: Local inference is slower
  - Response times depend on your hardware
  - Model size affects speed (7B model is relatively fast)
  - Consider using smaller models for faster responses

### Model Recommendations

For different use cases:

| Use Case | Recommended Model | Notes |
|----------|------------------|-------|
| Code generation | qwen2.5-coder:7b | Good balance of quality and speed |
| Fast responses | qwen2.5-coder:1.5b | Smaller, faster, less capable |
| Better quality | qwen2.5-coder:14b | Larger, slower, more capable |
| Vision support | llava:13b | Can process images |
| General purpose | llama3.1:8b | Good for non-coding tasks |

To change models:
1. Pull the model: `ollama pull <model-name>`
2. Update `.env`: `OLLAMA_MODEL=<model-name>`
3. Restart the proxy

## Troubleshooting

### Proxy won't start

**Error: Ollama service is not running**
```bash
# Start Ollama
ollama serve
```

**Error: Port 8000 is already in use**
```bash
# Change the port in .env
PROXY_PORT=8001

# Or kill the process using the port
lsof -ti:8000 | xargs kill -9
```

**Error: Model not found**
```bash
# Pull the model
ollama pull qwen2.5-coder:7b
```

### Claude Code errors

**Error: Connection refused**
- Make sure the proxy is running (`./start.sh`)
- Check the proxy port matches what's in setup-claude.sh

**Error: API key invalid**
- Make sure you've sourced setup-claude.sh: `source setup-claude.sh`
- The proxy accepts any API key (it's a dummy value)

**Claude Code tools not working**
- This is expected with models that don't support function calling
- The model will try to simulate tool calls with text
- Consider using a more capable model or testing with simpler tasks

### Response quality issues

**Responses are not as good as Claude**
- This is expected - Ollama models are different from Claude
- Try adjusting temperature in the request
- Consider using a larger model
- Note: Claude Code's prompts are optimized for Claude models

**Model is too slow**
- Use a smaller model (e.g., qwen2.5-coder:1.5b)
- Upgrade hardware (GPU acceleration helps)
- Reduce max_tokens to generate shorter responses

### Debug mode

Enable detailed logging:

1. Edit `.env`:
```bash
DEBUG=true
```

2. Restart the proxy

This will log all requests and responses for debugging.

## Advanced Configuration

### Using a Different Model

Edit `.env`:
```bash
OLLAMA_MODEL=llama3.1:8b
```

Then restart the proxy.

### Running on a Different Port

Edit `.env`:
```bash
PROXY_PORT=9000
```

Then restart the proxy and re-source setup-claude.sh.

### Using Remote Ollama

If Ollama is running on another machine:

Edit `.env`:
```bash
OLLAMA_ENDPOINT=http://192.168.1.100:11434
```

### Environment Variables for Claude Code Session

Instead of sourcing setup-claude.sh every time, add to your shell profile:

```bash
# Add to ~/.bashrc or ~/.zshrc
export ANTHROPIC_BASE_URL="http://localhost:8000"
export ANTHROPIC_API_KEY="ollama-proxy-dummy-key"
```

## Development

### Project Structure

```
ollama-proxy/
├── .env                 # Configuration
├── server.py            # Main proxy server
├── requirements.txt     # Python dependencies
├── start.sh            # Startup script
├── setup-claude.sh     # Claude Code configuration
└── README.md           # This file
```

### Modifying the Translation Logic

The translation logic is in `server.py`:

- `AnthropicToOllamaTranslator.translate_messages()` - Request translation
- `AnthropicToOllamaTranslator.translate_response()` - Response translation

You can modify these methods to:
- Add support for new content types
- Improve tool calling translation
- Handle model-specific quirks

### Adding New Endpoints

To add support for more Anthropic API endpoints:

1. Add a new route in `server.py`
2. Implement the translation logic
3. Forward to the appropriate Ollama endpoint

Example:
```python
@app.post("/v1/complete")
async def create_completion(request: Request):
    # Your implementation
    pass
```

## Testing

### Manual Testing

Test the proxy directly:

```bash
# Health check
curl http://localhost:8000/

# List models
curl http://localhost:8000/v1/models

# Send a message
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: test" \
  -d '{
    "model": "claude-3-opus-20240229",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 100
  }'
```

### Integration Testing

Test with Claude Code:

```bash
# Source the setup
source setup-claude.sh

# Simple test
claude "Say hello"

# Test with code
echo 'def hello(): print("hi")' > test.py
claude "Explain this code" test.py

# Interactive test
claude
# Then type some queries
```

## Uninstallation

To remove the proxy:

```bash
# Stop the proxy (Ctrl+C in the terminal running it)

# Remove environment variables
unset ANTHROPIC_BASE_URL
unset ANTHROPIC_API_KEY

# Remove the proxy directory
rm -rf ollama-proxy/
```

## FAQ

**Q: Can I use this with other tools that use the Anthropic API?**
A: Yes! Any tool that supports setting a custom API base URL can use this proxy.

**Q: Is this secure?**
A: The proxy runs locally and doesn't send data to the cloud. However, it accepts any API key, so don't expose it to the network.

**Q: Can I use streaming responses?**
A: Not currently, but streaming support can be added. Edit `server.py` and set `stream: True` in the Ollama request.

**Q: Why is it slower than Anthropic's API?**
A: Local inference on CPU/GPU is slower than Anthropic's optimized cloud infrastructure. Use smaller models or upgrade hardware for better performance.

**Q: Can I use multiple models?**
A: Currently, the proxy uses one model at a time (set in `.env`). You could modify the proxy to map different Anthropic model names to different Ollama models.

**Q: Will this work with future Claude Code updates?**
A: As long as Claude Code continues to use the Anthropic API format, this should work. API changes may require proxy updates.

## Contributing

This is a custom integration. To improve it:

1. Test with different Ollama models
2. Improve tool calling translation
3. Add streaming support
4. Optimize performance
5. Add more Anthropic API endpoints

## License

This proxy adapter is provided as-is for local use with Ollama and Claude Code.

## Support

For issues:
- Ollama problems: [https://github.com/ollama/ollama](https://github.com/ollama/ollama)
- Claude Code problems: [https://github.com/anthropics/claude-code](https://github.com/anthropics/claude-code)
- Proxy problems: Check the troubleshooting section above

## Acknowledgments

- Anthropic for Claude Code
- Ollama team for the local LLM runtime
- FastAPI for the Python web framework
