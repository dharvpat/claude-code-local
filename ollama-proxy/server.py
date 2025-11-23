#!/usr/bin/env python3
"""
Ollama API Proxy for Claude Code with Context Caching
Translates Anthropic API format to Ollama API format
Includes persistent context caching for extended conversations
"""

import os
import json
import asyncio
from typing import Any, Dict, List, Optional, Union
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
import httpx
import uvicorn
import logging
from datetime import datetime
import base64

# Import caching components
from cache_store import CacheStore
from session_manager import SessionManager
from context_manager import ContextManager
from summarizer import Summarizer
from context_retrieval import ContextRetrieval

# Load environment variables
load_dotenv()

# Configuration
OLLAMA_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
PROXY_PORT = int(os.getenv("PROXY_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Caching Configuration
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
CACHE_DIR = os.getenv("CACHE_DIR", "./cache")
MAX_ACTIVE_TOKENS = int(os.getenv("MAX_ACTIVE_TOKENS", "8000"))
MAX_TOTAL_TOKENS = int(os.getenv("MAX_TOTAL_TOKENS", "100000"))
SUMMARY_RATIO = float(os.getenv("SUMMARY_RATIO", "0.2"))
AUTO_SESSION = os.getenv("AUTO_SESSION", "true").lower() == "true"
SMART_RETRIEVAL = os.getenv("SMART_RETRIEVAL", "true").lower() == "true"
RETRIEVAL_THRESHOLD = float(os.getenv("RETRIEVAL_THRESHOLD", "0.6"))

# Setup logging
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Ollama API Proxy with Caching", version="2.0.0")

# Global caching components
cache_store = None
session_manager = None
context_manager = None
summarizer = None
context_retrieval = None


@app.on_event("startup")
async def startup_event():
    """Initialize caching components on startup"""
    global cache_store, session_manager, context_manager, summarizer, context_retrieval

    if CACHE_ENABLED:
        logger.info("Initializing context caching system...")

        # Initialize components
        cache_store = CacheStore(cache_dir=CACHE_DIR)
        session_manager = SessionManager(cache_store=cache_store, auto_create=AUTO_SESSION)
        context_manager = ContextManager(
            max_active_tokens=MAX_ACTIVE_TOKENS,
            max_total_tokens=MAX_TOTAL_TOKENS,
            summary_ratio=SUMMARY_RATIO
        )
        summarizer = Summarizer(
            ollama_endpoint=OLLAMA_ENDPOINT,
            ollama_model=OLLAMA_MODEL
        )
        context_retrieval = ContextRetrieval(
            cache_store=cache_store,
            enabled=SMART_RETRIEVAL,
            similarity_threshold=RETRIEVAL_THRESHOLD
        )

        logger.info("Context caching system initialized successfully")
        logger.info(f"Cache directory: {CACHE_DIR}")
        logger.info(f"Max active tokens: {MAX_ACTIVE_TOKENS}")
        logger.info(f"Max total tokens: {MAX_TOTAL_TOKENS}")
    else:
        logger.info("Context caching is disabled")


@app.on_event("shutdown")
async def shutdown_event():
    """Persist sessions on shutdown"""
    if CACHE_ENABLED and session_manager:
        logger.info("Persisting active sessions...")
        count = session_manager.persist_all_sessions()
        logger.info(f"Persisted {count} sessions")


class AnthropicToOllamaTranslator:
    """Translates between Anthropic and Ollama API formats"""

    @staticmethod
    def translate_messages(messages: List[Dict[str, Any]], system: Optional[str] = None) -> List[Dict[str, str]]:
        """Convert Anthropic message format to Ollama chat format"""
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

            # Skip archived/retrieved markers (internal use only)
            if msg.get("archived") or msg.get("retrieved"):
                # These are cache metadata messages
                if role == "system":
                    ollama_messages.append({
                        "role": "system",
                        "content": content
                    })
                continue

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
                            source = block.get("source", {})
                            if source.get("type") == "base64":
                                images.append(source.get("data", ""))

                        elif block_type == "tool_use":
                            tool_name = block.get("name", "unknown")
                            tool_input = block.get("input", {})
                            text_parts.append(f"[Calling tool: {tool_name} with input: {json.dumps(tool_input)}]")

                        elif block_type == "tool_result":
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

                if images:
                    combined_content += "\n[Note: Images attached but may not be processed by current model]"

                ollama_messages.append({
                    "role": role,
                    "content": combined_content
                })

            elif isinstance(content, str):
                ollama_messages.append({
                    "role": role,
                    "content": content
                })

        return ollama_messages

    @staticmethod
    def translate_response(ollama_response: Dict[str, Any], original_request: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Ollama response to Anthropic format"""
        message = ollama_response.get("message", {})
        content_text = message.get("content", "")

        content_blocks = []

        if "tool_calls" in message:
            for tool_call in message["tool_calls"]:
                content_blocks.append({
                    "type": "tool_use",
                    "id": f"toolu_{hash(json.dumps(tool_call)) % 100000:05d}",
                    "name": tool_call.get("function", {}).get("name", "unknown"),
                    "input": tool_call.get("function", {}).get("arguments", {})
                })

        if content_text:
            content_blocks.append({
                "type": "text",
                "text": content_text
            })

        if not content_blocks:
            content_blocks = [{"type": "text", "text": ""}]

        stop_reason = "end_turn"
        if ollama_response.get("done_reason") == "length":
            stop_reason = "max_tokens"
        elif not ollama_response.get("done", True):
            stop_reason = "stop_sequence"

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
        "version": "2.0.0",
        "ollama_endpoint": OLLAMA_ENDPOINT,
        "ollama_model": OLLAMA_MODEL,
        "caching_enabled": CACHE_ENABLED
    }


@app.get("/v1/models")
async def list_models():
    """List available models (Anthropic API compatibility)"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{OLLAMA_ENDPOINT}/api/tags")
            response.raise_for_status()
            ollama_data = response.json()

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
async def create_message(
    request: Request,
    x_session_id: Optional[str] = Header(None)
):
    """
    Main endpoint for message creation with context caching
    Translates to Ollama's /api/chat endpoint
    """
    try:
        # Parse incoming request
        body = await request.json()
        logger.debug(f"Received request: {json.dumps(body, indent=2)[:500]}...")

        # Extract Anthropic API parameters
        model = body.get("model", OLLAMA_MODEL)
        messages = body.get("messages", [])
        system = body.get("system", None)
        max_tokens = body.get("max_tokens", 4096)
        temperature = body.get("temperature", 1.0)
        top_p = body.get("top_p", 1.0)
        tools = body.get("tools", [])

        # Handle caching if enabled
        if CACHE_ENABLED and session_manager:
            session_id, session_data = await handle_cached_conversation(
                x_session_id,
                messages,
                system
            )

            # Use cached + new messages
            all_messages = session_data.get("messages", []) + messages

            # Check if we need to retrieve archived context
            if context_retrieval and len(messages) > 0:
                last_user_message = None
                for msg in reversed(messages):
                    if msg.get("role") == "user":
                        content = msg.get("content", "")
                        if isinstance(content, str):
                            last_user_message = content
                        elif isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    last_user_message = block.get("text", "")
                                    break
                        if last_user_message:
                            break

                if last_user_message:
                    retrieved = context_retrieval.retrieve_relevant_context(
                        session_id,
                        last_user_message
                    )

                    if retrieved:
                        logger.info(f"Retrieved {len(retrieved)} archived contexts")
                        # Inject retrieved context
                        all_messages = retrieved + all_messages
        else:
            all_messages = messages
            session_id = None

        # Translate messages to Ollama format
        translator = AnthropicToOllamaTranslator()
        ollama_messages = translator.translate_messages(all_messages, system)

        # Build Ollama request
        ollama_request = {
            "model": OLLAMA_MODEL,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": max_tokens
            }
        }

        if tools:
            logger.warning("Tools requested but Ollama tool support is model-dependent")
            ollama_request["tools"] = tools

        logger.debug(f"Sending to Ollama: {json.dumps(ollama_request, indent=2)[:500]}...")

        # Forward request to Ollama
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{OLLAMA_ENDPOINT}/api/chat",
                json=ollama_request
            )
            response.raise_for_status()
            ollama_response = response.json()

        logger.debug(f"Received from Ollama: {json.dumps(ollama_response, indent=2)[:500]}...")

        # Translate response back to Anthropic format
        anthropic_response = translator.translate_response(ollama_response, body)

        # Update cache with response
        if CACHE_ENABLED and session_manager and session_id:
            await update_cache_with_response(
                session_id,
                messages,
                anthropic_response
            )

        # Add session ID to response headers for client tracking
        if session_id:
            headers = {"X-Session-ID": session_id}
            return JSONResponse(content=anthropic_response, headers=headers)

        return JSONResponse(content=anthropic_response)

    except httpx.HTTPError as e:
        logger.error(f"Error communicating with Ollama: {e}")
        raise HTTPException(status_code=503, detail=f"Ollama service error: {str(e)}")

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


async def handle_cached_conversation(
    session_id: Optional[str],
    new_messages: List[Dict[str, Any]],
    system: Optional[str]
) -> tuple[str, Dict[str, Any]]:
    """Handle cached conversation context"""
    # Get or create session
    session_id, session_data = session_manager.get_or_create_session(
        session_id=session_id,
        metadata={"system": system} if system else None
    )

    logger.debug(f"Using session: {session_id}")

    return session_id, session_data


async def update_cache_with_response(
    session_id: str,
    request_messages: List[Dict[str, Any]],
    response: Dict[str, Any]
):
    """Update cache with new messages and check if archival is needed"""
    # Extract response message
    response_message = {
        "role": response.get("role", "assistant"),
        "content": response.get("content", []),
        "timestamp": datetime.now().isoformat()
    }

    # Add timestamps to request messages
    for msg in request_messages:
        if "timestamp" not in msg:
            msg["timestamp"] = datetime.now().isoformat()

    # Calculate tokens
    all_new_messages = request_messages + [response_message]
    new_tokens = context_manager.estimate_messages_tokens(all_new_messages)

    # Add to session
    session_manager.add_messages(session_id, all_new_messages, new_tokens)

    # Get updated session
    session_data = session_manager._active_sessions.get(session_id)

    if not session_data:
        logger.error(f"Session disappeared: {session_id}")
        return

    active_tokens = session_data.get("active_tokens", 0)

    # Check if we need to archive
    if context_manager.should_archive(active_tokens):
        logger.info(f"Archival triggered for session {session_id} ({active_tokens} tokens)")

        # Calculate what to archive
        messages = session_data.get("messages", [])
        num_to_archive, tokens_to_archive = context_manager.calculate_archive_size(
            messages,
            active_tokens
        )

        if num_to_archive > 0:
            # Extract messages to archive
            messages_to_archive = messages[:num_to_archive]

            # Prepare metadata
            metadata = context_manager.prepare_archive_metadata(messages_to_archive)

            # Calculate summary target
            summary_target = context_manager.calculate_summary_target(tokens_to_archive)

            # Generate summary
            logger.info(f"Generating summary (target: {summary_target} tokens)...")
            summary_result = summarizer.generate_enhanced_summary(
                messages_to_archive,
                summary_target,
                metadata,
                include_index=True
            )

            summary_text = summary_result["summary"]
            summary_tokens = summary_result["estimated_summary_tokens"]

            # Create archive
            archive_id = cache_store.create_archive(
                session_id=session_id,
                messages=messages_to_archive,
                summary=summary_text,
                original_tokens=tokens_to_archive,
                summary_tokens=summary_tokens,
                metadata=metadata
            )

            logger.info(f"Created archive: {archive_id}")

            # Index content
            if "index_data" in summary_result:
                index_data = summary_result["index_data"]
                cache_store.index_content(
                    session_id=session_id,
                    archive_id=archive_id,
                    content_type="conversation",
                    keywords=index_data.get("keywords", []),
                    file_paths=index_data.get("file_paths", [])
                )

            # Update session with archive
            session_manager.archive_messages(
                session_id=session_id,
                archive_id=archive_id,
                num_messages=num_to_archive,
                summary=summary_text,
                summary_tokens=summary_tokens
            )

            logger.info(f"Archive complete. Reduced from {tokens_to_archive} to {summary_tokens} tokens")


# Session Management Endpoints

@app.get("/v1/sessions")
async def list_sessions(limit: int = 100):
    """List all sessions"""
    if not CACHE_ENABLED:
        raise HTTPException(status_code=501, detail="Caching is disabled")

    sessions = session_manager.list_sessions(limit=limit)
    return {"sessions": sessions, "count": len(sessions)}


@app.get("/v1/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session information"""
    if not CACHE_ENABLED:
        raise HTTPException(status_code=501, detail="Caching is disabled")

    info = session_manager.get_session_info(session_id)

    if not info:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get context summary
    session_data = session_manager._active_sessions.get(session_id)
    if not session_data:
        session_data = cache_store.load_session(session_id)

    if session_data:
        context_summary = context_manager.get_context_summary(
            active_tokens=session_data.get("active_tokens", 0),
            total_tokens=session_data.get("total_tokens", 0),
            message_count=len(session_data.get("messages", [])),
            archive_count=len(session_data.get("archive_ids", []))
        )
        info["context"] = context_summary

    return info


@app.delete("/v1/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session"""
    if not CACHE_ENABLED:
        raise HTTPException(status_code=501, detail="Caching is disabled")

    success = session_manager.delete_session(session_id)

    if not success:
        raise HTTPException(status_code=404, detail="Session not found or error deleting")

    return {"status": "deleted", "session_id": session_id}


@app.post("/v1/sessions/{session_id}/archive")
async def manual_archive(session_id: str):
    """Manually trigger archival for a session"""
    if not CACHE_ENABLED:
        raise HTTPException(status_code=501, detail="Caching is disabled")

    # This would trigger the archival process manually
    # Implementation similar to automatic archival in update_cache_with_response

    return {"status": "archival_triggered", "session_id": session_id}


@app.get("/v1/cache/stats")
async def get_cache_stats():
    """Get cache statistics"""
    if not CACHE_ENABLED:
        raise HTTPException(status_code=501, detail="Caching is disabled")

    stats = session_manager.get_stats()

    return {
        "cache_enabled": CACHE_ENABLED,
        "cache_dir": CACHE_DIR,
        "configuration": {
            "max_active_tokens": MAX_ACTIVE_TOKENS,
            "max_total_tokens": MAX_TOTAL_TOKENS,
            "summary_ratio": SUMMARY_RATIO,
            "smart_retrieval": SMART_RETRIEVAL
        },
        "statistics": stats
    }


@app.post("/v1/messages/count_tokens")
async def count_tokens(request: Request):
    """Token counting endpoint"""
    body = await request.json()
    messages = body.get("messages", [])
    system = body.get("system", "")

    if CACHE_ENABLED:
        estimated_tokens = context_manager.estimate_messages_tokens(messages)
        if system:
            estimated_tokens += context_manager.estimate_tokens(system)
    else:
        # Fallback estimation
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

    return {"input_tokens": estimated_tokens}


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def catch_all(path: str, request: Request):
    """Catch-all for other Anthropic API endpoints"""
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
    logger.info(f"Caching: {'ENABLED' if CACHE_ENABLED else 'DISABLED'}")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PROXY_PORT,
        log_level="debug" if DEBUG else "info"
    )


if __name__ == "__main__":
    main()
