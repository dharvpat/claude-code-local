#!/usr/bin/env python3
"""
Ollama API Proxy for Claude Code
Translates Anthropic API format to Ollama API format
"""

import os
import json
import asyncio
from typing import Any, Dict, List, Optional, Union
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx
import uvicorn
import logging
from datetime import datetime
import base64

# Load environment variables
load_dotenv()

# Configuration
OLLAMA_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
PROXY_PORT = int(os.getenv("PROXY_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Setup logging
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Ollama API Proxy", version="1.0.0")


class AnthropicToOllamaTranslator:
    """Translates between Anthropic and Ollama API formats"""

    @staticmethod
    def translate_messages(messages: List[Dict[str, Any]], system: Optional[str] = None) -> List[Dict[str, str]]:
        """
        Convert Anthropic message format to Ollama chat format

        Anthropic format:
        [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}]

        Ollama format:
        [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}]
        """
        ollama_messages = []

        # Add system message if present
        if system:
            ollama_messages.append({
                "role": "system",
                "content": system
            })

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # Handle different content formats
            if isinstance(content, list):
                # Content blocks (text, image, tool_use, tool_result)
                text_parts = []
                images = []

                for block in content:
                    if isinstance(block, dict):
                        block_type = block.get("type", "text")

                        if block_type == "text":
                            text_parts.append(block.get("text", ""))

                        elif block_type == "image":
                            # Handle image content
                            source = block.get("source", {})
                            if source.get("type") == "base64":
                                images.append(source.get("data", ""))

                        elif block_type == "tool_use":
                            # Convert tool use to text representation for models without native tool support
                            tool_name = block.get("name", "unknown")
                            tool_input = block.get("input", {})
                            text_parts.append(f"[Calling tool: {tool_name} with input: {json.dumps(tool_input)}]")

                        elif block_type == "tool_result":
                            # Convert tool result to text
                            tool_use_id = block.get("tool_use_id", "")
                            result_content = block.get("content", "")
                            if isinstance(result_content, list):
                                result_text = " ".join([
                                    c.get("text", "") if isinstance(c, dict) else str(c)
                                    for c in result_content
                                ])
                            else:
                                result_text = str(result_content)
                            text_parts.append(f"[Tool result: {result_text}]")

                combined_content = "\n".join(text_parts)

                # For now, we'll add images as a note (full multimodal support depends on Ollama model)
                if images:
                    combined_content += "\n[Note: Images attached but may not be processed by current model]"

                ollama_messages.append({
                    "role": role,
                    "content": combined_content
                })

            elif isinstance(content, str):
                # Simple string content
                ollama_messages.append({
                    "role": role,
                    "content": content
                })

        return ollama_messages

    @staticmethod
    def translate_response(ollama_response: Dict[str, Any], original_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert Ollama response to Anthropic format

        Ollama response format:
        {
            "model": "qwen2.5-coder:7b",
            "created_at": "2023-08-04T08:52:19.385406455-07:00",
            "message": {"role": "assistant", "content": "response text"},
            "done": true,
            "total_duration": 5191566416,
            "prompt_eval_count": 26,
            "eval_count": 298
        }

        Anthropic response format:
        {
            "id": "msg_01XYZ",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "response text"}],
            "model": "claude-3-opus-20240229",
            "stop_reason": "end_turn",
            "stop_sequence": null,
            "usage": {
                "input_tokens": 26,
                "output_tokens": 298
            }
        }
        """
        message = ollama_response.get("message", {})
        content_text = message.get("content", "")

        # Try to parse tool calls if present in the response
        # Some Ollama models return function calls in structured format
        content_blocks = []

        # Check if response contains tool calls (model-specific format)
        if "tool_calls" in message:
            for tool_call in message["tool_calls"]:
                content_blocks.append({
                    "type": "tool_use",
                    "id": f"toolu_{hash(json.dumps(tool_call)) % 100000:05d}",
                    "name": tool_call.get("function", {}).get("name", "unknown"),
                    "input": tool_call.get("function", {}).get("arguments", {})
                })

        # Add text content
        if content_text:
            content_blocks.append({
                "type": "text",
                "text": content_text
            })

        # If no content blocks, add empty text
        if not content_blocks:
            content_blocks = [{"type": "text", "text": ""}]

        # Determine stop reason
        stop_reason = "end_turn"
        if ollama_response.get("done_reason") == "length":
            stop_reason = "max_tokens"
        elif not ollama_response.get("done", True):
            stop_reason = "stop_sequence"

        # Build Anthropic response
        anthropic_response = {
            "id": f"msg_{hash(str(datetime.now())) % 1000000:06d}",
            "type": "message",
            "role": "assistant",
            "content": content_blocks,
            "model": original_request.get("model", "claude-3-opus-20240229"),
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {
                "input_tokens": ollama_response.get("prompt_eval_count", 0),
                "output_tokens": ollama_response.get("eval_count", 0)
            }
        }

        return anthropic_response


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "Ollama API Proxy for Claude Code",
        "ollama_endpoint": OLLAMA_ENDPOINT,
        "ollama_model": OLLAMA_MODEL
    }


@app.get("/v1/models")
async def list_models():
    """
    List available models (Anthropic API compatibility)
    Maps to Ollama's /api/tags endpoint
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{OLLAMA_ENDPOINT}/api/tags")
            response.raise_for_status()
            ollama_data = response.json()

            # Convert Ollama format to Anthropic format
            models = []
            for model in ollama_data.get("models", []):
                models.append({
                    "id": model.get("name", "unknown"),
                    "type": "model",
                    "display_name": model.get("name", "unknown"),
                    "created_at": model.get("modified_at", datetime.now().isoformat())
                })

            return {"data": models}

    except httpx.HTTPError as e:
        logger.error(f"Error fetching models from Ollama: {e}")
        raise HTTPException(status_code=503, detail=f"Ollama service unavailable: {str(e)}")


@app.post("/v1/messages")
async def create_message(request: Request):
    """
    Main endpoint for message creation (Anthropic API compatibility)
    Translates to Ollama's /api/chat endpoint
    """
    try:
        # Parse incoming request
        body = await request.json()
        logger.debug(f"Received request: {json.dumps(body, indent=2)}")

        # Extract Anthropic API parameters
        model = body.get("model", OLLAMA_MODEL)
        messages = body.get("messages", [])
        system = body.get("system", None)
        max_tokens = body.get("max_tokens", 4096)
        temperature = body.get("temperature", 1.0)
        top_p = body.get("top_p", 1.0)
        tools = body.get("tools", [])

        # Translate messages to Ollama format
        translator = AnthropicToOllamaTranslator()
        ollama_messages = translator.translate_messages(messages, system)

        # Build Ollama request
        ollama_request = {
            "model": OLLAMA_MODEL,  # Use configured model
            "messages": ollama_messages,
            "stream": False,  # No streaming for now
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": max_tokens
            }
        }

        # Add tools if supported (note: depends on Ollama model capabilities)
        if tools:
            logger.warning("Tools requested but Ollama tool support is model-dependent")
            # Some Ollama models support tools via 'tools' parameter
            # Format may need adjustment based on model
            ollama_request["tools"] = tools

        logger.debug(f"Sending to Ollama: {json.dumps(ollama_request, indent=2)}")

        # Forward request to Ollama
        async with httpx.AsyncClient(timeout=300.0) as client:  # 5 min timeout for long generations
            response = await client.post(
                f"{OLLAMA_ENDPOINT}/api/chat",
                json=ollama_request
            )
            response.raise_for_status()
            ollama_response = response.json()

        logger.debug(f"Received from Ollama: {json.dumps(ollama_response, indent=2)}")

        # Translate response back to Anthropic format
        anthropic_response = translator.translate_response(ollama_response, body)

        logger.debug(f"Sending response: {json.dumps(anthropic_response, indent=2)}")

        return JSONResponse(content=anthropic_response)

    except httpx.HTTPError as e:
        logger.error(f"Error communicating with Ollama: {e}")
        raise HTTPException(status_code=503, detail=f"Ollama service error: {str(e)}")

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post("/v1/messages/count_tokens")
async def count_tokens(request: Request):
    """
    Token counting endpoint (Anthropic API compatibility)
    Provides rough estimate since Ollama doesn't have native token counting
    """
    body = await request.json()
    messages = body.get("messages", [])
    system = body.get("system", "")

    # Rough token estimation (4 chars ≈ 1 token)
    total_chars = len(system)
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    total_chars += len(block.get("text", ""))

    estimated_tokens = total_chars // 4

    return {
        "input_tokens": estimated_tokens
    }


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def catch_all(path: str, request: Request):
    """
    Catch-all for other Anthropic API endpoints
    Logs the request and returns a not implemented response
    """
    logger.warning(f"Unsupported endpoint called: /v1/{path}")
    return JSONResponse(
        status_code=501,
        content={
            "error": {
                "type": "not_implemented",
                "message": f"Endpoint /v1/{path} is not implemented in this proxy"
            }
        }
    )


def main():
    """Start the proxy server"""
    logger.info(f"Starting Ollama API Proxy on port {PROXY_PORT}")
    logger.info(f"Forwarding to Ollama at {OLLAMA_ENDPOINT}")
    logger.info(f"Using model: {OLLAMA_MODEL}")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PROXY_PORT,
        log_level="debug" if DEBUG else "info"
    )


if __name__ == "__main__":
    main()
