# Tool Support in Ollama Proxy

## TL;DR

✅ **Yes, Claude Code tools will work!**

Tools are executed **client-side** in Claude Code, not on the server. The proxy just passes tool requests and results back and forth. However, the **quality** depends on whether your Ollama model understands function calling.

## Architecture

### Where Tools Are Executed

```
┌─────────────────────────────────────────────┐
│  Claude Code CLI (YOUR COMPUTER)            │
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │ Tools (Implemented Here):            │  │
│  │ • Read    - Read files               │  │
│  │ • Write   - Write files              │  │
│  │ • Edit    - Edit files               │  │
│  │ • Bash    - Run commands             │  │
│  │ • Glob    - Find files               │  │
│  │ • Grep    - Search content           │  │
│  │ • WebFetch - Fetch URLs              │  │
│  │ • ... and many more                  │  │
│  └──────────────────────────────────────┘  │
│                    ↕                        │
│         API Requests/Responses              │
└─────────────────────────────────────────────┘
                     ↕
┌─────────────────────────────────────────────┐
│  Ollama Proxy (TRANSLATION LAYER)           │
│  • Translates Anthropic ↔ Ollama format    │
│  • Passes tool messages through            │
│  • Does NOT execute tools                  │
└─────────────────────────────────────────────┘
                     ↕
┌─────────────────────────────────────────────┐
│  Ollama (LOCAL LLM)                         │
│  • Decides when to use tools                │
│  • Processes tool results                   │
│  • Generates responses                      │
└─────────────────────────────────────────────┘
```

## How Tool Calling Works

### Step-by-Step Flow

1. **User Request**: "Read the file server.py and explain it"

2. **Claude Code** receives the request and prepares API call with tool definitions:
   ```json
   {
     "messages": [{"role": "user", "content": "Read server.py"}],
     "tools": [
       {
         "name": "read_file",
         "description": "Read a file",
         "input_schema": {...}
       }
     ]
   }
   ```

3. **Proxy** translates and forwards to Ollama

4. **Ollama** responds (ideally) with:
   ```json
   {
     "role": "assistant",
     "content": [
       {
         "type": "tool_use",
         "name": "read_file",
         "input": {"file_path": "server.py"}
       }
     ]
   }
   ```

5. **Claude Code** sees the tool_use, executes `read_file` locally

6. **Claude Code** sends tool result back:
   ```json
   {
     "messages": [
       {...previous messages...},
       {
         "role": "user",
         "content": [
           {
             "type": "tool_result",
             "content": "#!/usr/bin/env python3\n..."
           }
         ]
       }
     ]
   }
   ```

7. **Ollama** processes the file contents and generates final response

8. **Claude Code** displays the response to you

## Current Implementation

### What the Proxy Does

The proxy's `AnthropicToOllamaTranslator` handles three tool-related content types:

#### 1. Tool Definitions (Request)
```python
# Passed through to Ollama (model-dependent support)
if tools:
    ollama_request["tools"] = tools
```

#### 2. Tool Use Blocks (Assistant → Tools)
```python
# Converted to text as fallback
elif block_type == "tool_use":
    tool_name = block.get("name", "unknown")
    tool_input = block.get("input", {})
    text_parts.append(
        f"[Calling tool: {tool_name} with input: {json.dumps(tool_input)}]"
    )
```

#### 3. Tool Result Blocks (Tools → Assistant)
```python
# Converted to text
elif block_type == "tool_result":
    result_content = block.get("content", "")
    text_parts.append(f"[Tool result: {result_text}]")
```

### What This Means

**✅ Tools WILL execute** (Claude Code handles this)
**⚠️ Tool calling quality depends on model**

## Model Compatibility

### qwen2.5-coder:7b (Default)

**Function Calling**: ⚠️ Limited
- May not generate native `tool_use` blocks
- Can understand tool results as text
- Will respond conversationally about tools

**Workaround**: The model sees:
```
User: Read server.py
Assistant: [Calling tool: read_file with input: {"file_path": "server.py"}]
User: [Tool result: #!/usr/bin/env python3...]
Assistant: Based on the file, here's what it does...
```

This works, but less elegantly than native tool calling.

### Better Models for Tools

**Recommended for better tool support:**

| Model | Tool Support | Notes |
|-------|-------------|-------|
| qwen2.5-coder:14b | Good | Better reasoning, native function calling |
| deepseek-r1:14b | Excellent | Strong reasoning + tool use |
| llama3.1:70b | Excellent | Native function calling (requires more RAM) |
| mistral-large | Excellent | Strong tool calling support |

To switch models:
```bash
# Edit .env
OLLAMA_MODEL=deepseek-r1:14b

# Pull the model
ollama pull deepseek-r1:14b

# Restart proxy
./start.sh
```

## Testing Tool Support

Run the test script:

```bash
python test_tools.py
```

This tests:
1. Can tool definitions be passed?
2. Can tool results be processed?

## Expected Behavior

### With Native Tool Support (Good Model)

```
You: Read server.py and find the bug

Claude Code:
  → Calls Read tool
  ← Gets file contents
  → Sends to proxy → Ollama
  ← Ollama requests to use grep tool
  → Calls Grep tool
  ← Gets search results
  → Sends to proxy → Ollama
  ← Ollama provides analysis

Result: ✅ Multi-tool workflow works perfectly
```

### Without Native Tool Support (qwen2.5-coder:7b)

```
You: Read server.py and find the bug

Claude Code:
  → Calls Read tool (Claude Code decides this, not model)
  ← Gets file contents
  → Sends to proxy → Ollama
  ← Ollama analyzes text, responds conversationally

Result: ⚠️ Works, but model doesn't request additional tools
        You need to be more explicit: "Now grep for 'error'"
```

## Improving Tool Support

### Option 1: Use a Better Model

```bash
OLLAMA_MODEL=deepseek-r1:14b
```

### Option 2: Enhanced Tool Translation

We could enhance the proxy to better translate tool formats. Currently, tools are converted to text, but we could:

1. **Detect tool-like text in responses** and convert back to tool_use
2. **Add tool prompting** to encourage tool usage
3. **Map Ollama's function format** to Anthropic's format

Example enhancement (not currently implemented):
```python
# In translator
response_text = "I need to read the file server.py"

# Detect intent
if "read" in response_text and "file" in response_text:
    # Convert to tool_use block
    return {
        "type": "tool_use",
        "name": "read_file",
        "input": {"file_path": extract_filepath(response_text)}
    }
```

### Option 3: Prompt Engineering

Add system prompt to encourage tool use:
```python
system_prompt = """You have access to tools. When you need information:
- Use read_file to read files
- Use bash to run commands
- Use grep to search

Always request tools using the format:
[TOOL: tool_name]
[INPUT: {"param": "value"}]
"""
```

## Troubleshooting

### Tools Don't Work At All

**Check**: Is Claude Code receiving tool definitions?

Debug by enabling logging:
```bash
DEBUG=true
```

Look for tool definitions in proxy logs.

**Check**: Is the model responding?

Some models might not understand tools at all. Try a different model.

### Model Doesn't Request Tools

**Expected** with qwen2.5-coder:7b. The model processes tool results but doesn't proactively request tools.

**Solution**:
- Use a better model with native function calling
- Be explicit in your prompts: "First read the file, then grep for errors"
- Claude Code might still execute tools based on its own logic

### Tool Results Not Processed

**Check**: Are tool results being sent correctly?

The proxy converts them to text, which all models should understand.

If this fails, it's likely a proxy bug - please report!

## Real-World Usage

### Scenario 1: File Operations

```bash
claude "Analyze server.py and suggest improvements"
```

**What happens:**
1. Claude Code calls Read tool → reads server.py
2. Sends file contents to proxy → Ollama
3. Ollama analyzes and responds
4. ✅ Works with any model

**Note**: Model doesn't request the Read - Claude Code does based on your prompt.

### Scenario 2: Multi-Tool Workflow

```bash
claude "Find all TODO comments in Python files"
```

**With good model (deepseek-r1):**
1. Model requests Glob tool → find *.py files
2. Model requests Grep tool → search for TODO
3. Model summarizes results
4. ✅ Autonomous tool use

**With qwen2.5-coder:7b:**
1. You might need to be explicit: "First use glob to find .py files"
2. Then: "Now grep those files for TODO"
3. ⚠️ More manual, but works

### Scenario 3: Code Generation

```bash
claude "Create a new FastAPI endpoint for /users"
```

**What happens:**
1. Claude Code might call Write tool based on response
2. Proxy passes through
3. ✅ Works fine - tools execute client-side

## Best Practices

1. **Use explicit prompts** with limited models:
   - ✅ "Read server.py then search for 'bug'"
   - ❌ "Find the bug in server.py" (may not request tools)

2. **Upgrade models** for autonomous workflows:
   - qwen2.5-coder:7b → qwen2.5-coder:14b
   - Or use deepseek-r1:14b

3. **Monitor tool usage** in logs:
   ```bash
   DEBUG=true ./start.sh
   ```

4. **Test tool workflows** before relying on them:
   ```bash
   python test_tools.py
   ```

## FAQ

**Q: Will `Read`, `Write`, `Edit`, `Bash` tools work?**
A: ✅ Yes! They're executed by Claude Code, not the proxy.

**Q: Why doesn't the model request tools?**
A: The model needs native function calling support. qwen2.5-coder:7b has limited support. Use a better model.

**Q: Can I improve tool support?**
A: Yes! Use a better model (deepseek-r1:14b, qwen2.5-coder:14b, etc.)

**Q: Will the proxy block or break tools?**
A: ❌ No. The proxy just translates formats. Tools always execute client-side.

**Q: What if I see "Tools requested but Ollama tool support is model-dependent"?**
A: This is a warning that your model might not support native function calling. Tools will still work, but the quality depends on the model.

**Q: Can I use Claude Code normally?**
A: ✅ Yes! Most basic tool usage works fine. Complex autonomous tool chaining needs a better model.

## Summary

| Aspect | Status | Notes |
|--------|--------|-------|
| Tool Execution | ✅ Always works | Client-side in Claude Code |
| Tool Results | ✅ Processed | Converted to text |
| Tool Requests | ⚠️ Model-dependent | qwen2.5-coder:7b limited |
| Basic Workflows | ✅ Works | "Read X, analyze Y" |
| Autonomous Workflows | ⚠️ Needs better model | deepseek-r1:14b recommended |
| Proxy Blocking | ❌ Never | Just translates messages |

## Conclusion

**The proxy will NOT get stuck!**

Tools are client-side, so they'll execute regardless of the model. The Ollama model just needs to understand what to do with tool results, which even basic models can handle.

For best results:
- ✅ Basic use: qwen2.5-coder:7b works fine
- 🚀 Power user: upgrade to deepseek-r1:14b or qwen2.5-coder:14b

Happy coding! 🛠️
