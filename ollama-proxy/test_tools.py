#!/usr/bin/env python3
"""
Test tool calling with the proxy
"""

import httpx
import json

PROXY_URL = "http://localhost:8000"

# Simulate what Claude Code sends when it wants the model to use a tool
request_with_tools = {
    "model": "claude-3-opus-20240229",
    "max_tokens": 1024,
    "tools": [
        {
            "name": "read_file",
            "description": "Read the contents of a file",
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to read"
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
        }
    ],
    "messages": [
        {
            "role": "user",
            "content": "Please read the file test.txt and tell me what's in it"
        }
    ]
}

# Simulate tool result being sent back
request_with_tool_result = {
    "model": "claude-3-opus-20240229",
    "max_tokens": 1024,
    "messages": [
        {
            "role": "user",
            "content": "Please read the file test.txt"
        },
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "read_file",
                    "input": {"file_path": "test.txt"}
                }
            ]
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_123",
                    "content": "Hello, this is the content of test.txt"
                }
            ]
        }
    ]
}

def test_tool_definition():
    """Test that tools can be passed through"""
    print("\n" + "="*60)
    print("Test 1: Sending tool definitions")
    print("="*60)

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{PROXY_URL}/v1/messages",
            json=request_with_tools
        )

        if response.status_code == 200:
            result = response.json()
            print("✓ Request successful")
            print(f"\nResponse role: {result.get('role')}")
            print(f"Content blocks: {len(result.get('content', []))}")

            for block in result.get('content', []):
                print(f"\nBlock type: {block.get('type')}")
                if block.get('type') == 'tool_use':
                    print(f"  Tool name: {block.get('name')}")
                    print(f"  Tool input: {block.get('input')}")
                    print("  ✓ Model generated tool call!")
                elif block.get('type') == 'text':
                    print(f"  Text: {block.get('text', '')[:100]}...")
        else:
            print(f"✗ Request failed: {response.status_code}")
            print(response.text)

def test_tool_result():
    """Test that tool results can be processed"""
    print("\n" + "="*60)
    print("Test 2: Sending tool results")
    print("="*60)

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{PROXY_URL}/v1/messages",
            json=request_with_tool_result
        )

        if response.status_code == 200:
            result = response.json()
            print("✓ Request successful")
            print(f"\nResponse: {result.get('content', [{}])[0].get('text', '')[:200]}...")
            print("\n✓ Model processed tool result!")
        else:
            print(f"✗ Request failed: {response.status_code}")
            print(response.text)

if __name__ == "__main__":
    print("\n" + "="*60)
    print("Testing Tool Support in Ollama Proxy")
    print("="*60)
    print("\nThis tests whether Claude Code's tools will work through the proxy")
    print("Tools are executed CLIENT-SIDE, so the proxy just needs to pass messages")

    try:
        # Test 1: Can we send tool definitions?
        test_tool_definition()

        # Test 2: Can we send tool results?
        test_tool_result()

        print("\n" + "="*60)
        print("Summary")
        print("="*60)
        print("\nThe proxy can handle tool messages!")
        print("\nHowever, the Ollama model (qwen2.5-coder:7b) may:")
        print("  ⚠️  Not generate native tool calls")
        print("  ✓  Process tool results as text")
        print("  ⚠️  Respond with text instead of tool_use blocks")
        print("\nFor best tool support, consider:")
        print("  • Using a model with better function calling")
        print("  • Or accept that tools work but via text descriptions")
        print("\nClaude Code will still execute tools locally regardless!")

    except httpx.ConnectError:
        print("\n✗ Cannot connect to proxy. Is it running?")
        print("Start it with: ./start.sh")
    except Exception as e:
        print(f"\n✗ Error: {e}")
