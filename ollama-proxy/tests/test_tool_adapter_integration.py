#!/usr/bin/env python3
"""
Integration Tests for Universal Tool Adapter
Tests the complete tool adapter workflow with the proxy
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import json
import pytest

PROXY_URL = "http://localhost:8000"


class TestToolAdapterIntegration:
    """Integration tests for tool adapter"""

    def test_tool_adapter_info(self):
        """Test getting tool adapter information"""
        print("\n=== Test: Get Tool Adapter Info ===")

        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{PROXY_URL}/v1/tool_adapter/info")

            assert response.status_code == 200, f"Failed: {response.status_code}"

            data = response.json()

            assert data["enabled"] == True, "Tool adapter should be enabled"
            assert "model" in data, "Should have model info"
            assert "tier" in data["model"], "Should have tier info"

            print(f"✓ Tool Adapter Info Retrieved")
            print(f"  Model: {data['model']['model']}")
            print(f"  Tier: {data['model']['tier']} - {data['model']['tier_name']}")
            print(f"  Description: {data['model']['description']}")

    def test_tool_adapter_test_endpoint(self):
        """Test the tool adapter test endpoint"""
        print("\n=== Test: Tool Adapter Test Endpoint ===")

        with httpx.Client(timeout=10.0) as client:
            response = client.post(f"{PROXY_URL}/v1/tool_adapter/test")

            assert response.status_code == 200, f"Failed: {response.status_code}"

            data = response.json()

            assert "tier" in data, "Should have tier info"
            assert "recommendation" in data, "Should have recommendation"

            print(f"✓ Tool Adapter Test Complete")
            print(f"  Tier: {data['tier']}")
            print(f"  Supports Native: {data['supports_native']}")
            print(f"  Recommendation: {data['recommendation']}")

    def test_simple_message_with_tools(self):
        """Test sending a message with tool definitions"""
        print("\n=== Test: Message with Tool Definitions ===")

        request = {
            "model": "claude-3-opus-20240229",
            "max_tokens": 500,
            "tools": [
                {
                    "name": "read_file",
                    "description": "Read a file",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"}
                        },
                        "required": ["file_path"]
                    }
                }
            ],
            "messages": [
                {
                    "role": "user",
                    "content": "Read the file called server.py"
                }
            ]
        }

        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{PROXY_URL}/v1/messages",
                json=request
            )

            assert response.status_code == 200, f"Failed: {response.status_code}"

            data = response.json()

            assert "content" in data, "Should have content"
            assert isinstance(data["content"], list), "Content should be a list"

            print(f"✓ Message with tools processed")
            print(f"  Content blocks: {len(data['content'])}")

            for i, block in enumerate(data["content"]):
                print(f"  Block {i+1}: {block.get('type', 'unknown')}")

                if block.get("type") == "tool_use":
                    print(f"    ✓ Tool detected: {block.get('name')}")
                    print(f"    Input: {block.get('input')}")
                elif block.get("type") == "text":
                    print(f"    Text: {block.get('text', '')[:100]}...")

    def test_multiple_tools(self):
        """Test with multiple tool definitions"""
        print("\n=== Test: Multiple Tool Definitions ===")

        tools = [
            {
                "name": "read_file",
                "description": "Read a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"}
                    }
                }
            },
            {
                "name": "write_file",
                "description": "Write to a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "content": {"type": "string"}
                    }
                }
            },
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
        ]

        request = {
            "model": "claude-3-opus-20240229",
            "max_tokens": 200,
            "tools": tools,
            "messages": [
                {
                    "role": "user",
                    "content": "What tools do you have available?"
                }
            ]
        }

        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{PROXY_URL}/v1/messages",
                json=request
            )

            assert response.status_code == 200

            data = response.json()

            print(f"✓ Multiple tools processed")
            print(f"  Sent {len(tools)} tools")
            print(f"  Response: {data['content'][0].get('text', '')[:150]}...")


def run_tests():
    """Run all tests"""
    print("\n" + "="*70)
    print("TOOL ADAPTER INTEGRATION TESTS")
    print("="*70)
    print("\nNOTE: Proxy must be running on http://localhost:8000")
    print("Start it with: ./start.sh\n")

    tests = TestToolAdapterIntegration()

    try:
        # Test 1: Info endpoint
        tests.test_tool_adapter_info()

        # Test 2: Test endpoint
        tests.test_tool_adapter_test_endpoint()

        # Test 3: Simple message with tools
        tests.test_simple_message_with_tools()

        # Test 4: Multiple tools
        tests.test_multiple_tools()

        print("\n" + "="*70)
        print("✓ ALL TESTS PASSED")
        print("="*70)

    except httpx.ConnectError:
        print("\n" + "="*70)
        print("✗ ERROR: Cannot connect to proxy")
        print("="*70)
        print("\nMake sure the proxy is running:")
        print("  cd ollama-proxy")
        print("  ./start.sh")
        sys.exit(1)

    except AssertionError as e:
        print("\n" + "="*70)
        print(f"✗ TEST FAILED: {e}")
        print("="*70)
        sys.exit(1)

    except Exception as e:
        print("\n" + "="*70)
        print(f"✗ ERROR: {e}")
        print("="*70)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
