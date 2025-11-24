#!/usr/bin/env python3
"""
Test whether Ollama models understand tool definitions
"""

import httpx
import json

PROXY_URL = "http://localhost:8000"

def test_tool_awareness():
    """
    Test if the model understands it has tools available
    """
    print("\n" + "="*70)
    print("TEST: Does the model know tools exist?")
    print("="*70)

    request = {
        "model": "claude-3-opus-20240229",
        "max_tokens": 500,
        "tools": [
            {
                "name": "read_file",
                "description": "Read the contents of a file from the filesystem",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file"
                        }
                    },
                    "required": ["file_path"]
                }
            },
            {
                "name": "write_file",
                "description": "Write content to a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["file_path", "content"]
                }
            },
            {
                "name": "bash",
                "description": "Execute a bash command",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"}
                    },
                    "required": ["command"]
                }
            }
        ],
        "messages": [
            {
                "role": "user",
                "content": "I need you to read the file called 'test.txt'. What should you do?"
            }
        ]
    }

    print("\nSending request with tool definitions...")
    print("Tools provided: read_file, write_file, bash")
    print("User request: 'Read the file called test.txt'")
    print("\nExpected behavior:")
    print("  ✓ Model should respond with tool_use for read_file")
    print("  ✓ Input should be {file_path: 'test.txt'}")

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{PROXY_URL}/v1/messages",
                json=request
            )

            if response.status_code != 200:
                print(f"\n✗ Request failed: {response.status_code}")
                print(response.text)
                return False

            result = response.json()
            print("\n" + "-"*70)
            print("RESPONSE FROM MODEL:")
            print("-"*70)

            content_blocks = result.get('content', [])

            found_tool_use = False
            for i, block in enumerate(content_blocks):
                block_type = block.get('type')
                print(f"\nBlock {i+1}: {block_type}")

                if block_type == 'tool_use':
                    found_tool_use = True
                    print(f"  ✓ Tool Name: {block.get('name')}")
                    print(f"  ✓ Tool Input: {json.dumps(block.get('input'), indent=4)}")
                    print("\n  ✅ SUCCESS: Model generated a tool_use block!")

                elif block_type == 'text':
                    text = block.get('text', '')
                    print(f"  Text: {text[:200]}...")

                    # Check if text mentions tools
                    if any(word in text.lower() for word in ['read', 'file', 'tool', 'function']):
                        print("  ⚠️  Model responded with text about tools, not tool_use")

            print("\n" + "="*70)
            if found_tool_use:
                print("RESULT: ✅ Model understands and uses tools!")
                print("="*70)
                return True
            else:
                print("RESULT: ❌ Model did NOT generate tool_use blocks")
                print("The model either:")
                print("  • Doesn't understand Anthropic's tool format")
                print("  • Isn't trained for function calling")
                print("  • Responded conversationally instead of using tools")
                print("="*70)
                return False

    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False


def test_explicit_tool_request():
    """
    Test with a very explicit request to use a specific tool
    """
    print("\n\n" + "="*70)
    print("TEST: Explicit tool usage request")
    print("="*70)

    request = {
        "model": "claude-3-opus-20240229",
        "max_tokens": 500,
        "tools": [
            {
                "name": "bash",
                "description": "Execute a bash command",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"}
                    }
                }
            }
        ],
        "messages": [
            {
                "role": "user",
                "content": "Use the bash tool to run the command 'ls -la'. You MUST respond with a tool_use block."
            }
        ]
    }

    print("\nVery explicit request: 'Use the bash tool... You MUST respond with tool_use'")

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{PROXY_URL}/v1/messages",
                json=request
            )

            if response.status_code != 200:
                print(f"\n✗ Failed: {response.status_code}")
                return False

            result = response.json()
            content = result.get('content', [])

            has_tool_use = any(b.get('type') == 'tool_use' for b in content)

            if has_tool_use:
                print("✅ Model responded with tool_use even when explicitly asked")
            else:
                print("❌ Model STILL didn't generate tool_use, even when explicitly requested")
                print("\nResponse:")
                for block in content:
                    if block.get('type') == 'text':
                        print(f"  {block.get('text', '')[:300]}")

            return has_tool_use

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_system_prompt_for_tools():
    """
    Test if adding system prompt helps model understand tools
    """
    print("\n\n" + "="*70)
    print("TEST: Using system prompt to explain tools")
    print("="*70)

    request = {
        "model": "claude-3-opus-20240229",
        "max_tokens": 500,
        "system": """You have access to tools that you can call. When you need to use a tool, respond with a JSON object like this:
{
  "type": "tool_use",
  "name": "tool_name",
  "input": {
    "parameter": "value"
  }
}

Available tools:
- read_file: Read a file
- write_file: Write to a file
- bash: Execute a command
""",
        "tools": [
            {
                "name": "read_file",
                "description": "Read a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"}
                    }
                }
            }
        ],
        "messages": [
            {
                "role": "user",
                "content": "Read the file config.json"
            }
        ]
    }

    print("\nAdded system prompt explaining tool format...")

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{PROXY_URL}/v1/messages",
                json=request
            )

            if response.status_code != 200:
                print(f"✗ Failed: {response.status_code}")
                return False

            result = response.json()
            content = result.get('content', [])

            has_tool_use = any(b.get('type') == 'tool_use' for b in content)

            if has_tool_use:
                print("✅ System prompt helped! Model generated tool_use")
            else:
                print("❌ System prompt didn't help")

            return has_tool_use

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "="*70)
    print("OLLAMA MODEL TOOL UNDERSTANDING TEST")
    print("="*70)
    print("\nThis tests whether Ollama models understand and use tools")
    print("the way Claude models do.")
    print("\nCritical question: Can the model generate tool_use blocks?")

    try:
        results = []

        # Test 1: Basic tool awareness
        results.append(("Basic tool usage", test_tool_awareness()))

        # Test 2: Explicit request
        results.append(("Explicit tool request", test_explicit_tool_request()))

        # Test 3: System prompt
        results.append(("System prompt approach", test_system_prompt_for_tools()))

        print("\n\n" + "="*70)
        print("SUMMARY")
        print("="*70)

        for test_name, passed in results:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status}: {test_name}")

        passed_count = sum(1 for _, p in results if p)
        total_count = len(results)

        print("\n" + "="*70)
        if passed_count == 0:
            print("❌ CRITICAL: Model does NOT understand tool calling")
            print("\nThis means:")
            print("  • Claude Code tools will NOT work autonomously")
            print("  • The model won't request tools on its own")
            print("  • You'll need to explicitly manage file operations")
            print("\nRecommendations:")
            print("  1. Use a model with better function calling (deepseek-r1:14b)")
            print("  2. Or accept limited tool usage")
            print("  3. Consider implementing a tool adapter (see below)")
        elif passed_count < total_count:
            print("⚠️  PARTIAL: Model has limited tool understanding")
            print("\nSome approaches work, consider using system prompts")
        else:
            print("✅ EXCELLENT: Model fully understands tools!")
            print("\nClaude Code should work great!")
        print("="*70)

    except httpx.ConnectError:
        print("\n✗ Cannot connect to proxy")
        print("Start it with: ./start.sh")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
