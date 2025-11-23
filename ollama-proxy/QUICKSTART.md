# Quick Start Guide

Get Claude Code working with Ollama in 3 steps!

## Prerequisites

Make sure you have:
- ✓ Ollama installed and running
- ✓ Python 3.8+
- ✓ Claude Code installed

## Step 1: Start Ollama

```bash
# In terminal 1
ollama serve
```

## Step 2: Start the Proxy

```bash
# In terminal 2
cd ollama-proxy
./start.sh
```

The script will automatically:
- Check prerequisites
- Pull the model if needed
- Set up Python virtual environment
- Install dependencies
- Start the proxy server

## Step 3: Configure Claude Code

```bash
# In terminal 3 (your working terminal)
cd ollama-proxy
source setup-claude.sh
```

## You're Done!

Now use Claude Code normally:

```bash
claude "Hello, how are you?"
```

All requests will go to your local Ollama instance instead of the cloud.

## Testing

Verify the proxy is working:

```bash
# In the same terminal where you sourced setup-claude.sh
cd ollama-proxy
./test_proxy.sh
```

## Stopping

- Press Ctrl+C in terminal 2 to stop the proxy
- Close terminal 1 to stop Ollama (or leave it running)
- Run `unset ANTHROPIC_BASE_URL ANTHROPIC_API_KEY` in terminal 3 to reset Claude Code

## Troubleshooting

**"Connection refused" error**
- Make sure the proxy is running (step 2)
- Make sure you sourced setup-claude.sh (step 3)

**"Ollama service is not running" error**
- Start Ollama with `ollama serve` (step 1)

**Slow responses**
- This is normal for local inference
- Consider using a smaller model (edit .env)
- Or upgrade your hardware

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Customize settings in `.env`
- Try different Ollama models

## Configuration Files

| File | Purpose |
|------|---------|
| `.env` | Configuration (model, ports, etc.) |
| `start.sh` | Start the proxy server |
| `setup-claude.sh` | Configure Claude Code environment |
| `test_proxy.sh` | Test the proxy |

## Default Settings

- Ollama Model: `qwen2.5-coder:7b`
- Ollama Endpoint: `http://localhost:11434`
- Proxy Port: `8000`

Edit `.env` to change these.
