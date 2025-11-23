"""
Summarization Engine
Uses Ollama to generate summaries of archived context
"""

import httpx
import logging
from typing import List, Dict, Any, Optional
import json

logger = logging.getLogger(__name__)


class Summarizer:
    """Generates summaries of conversation context using Ollama"""

    def __init__(
        self,
        ollama_endpoint: str = "http://localhost:11434",
        ollama_model: str = "qwen2.5-coder:7b",
        timeout: int = 120
    ):
        """
        Initialize Summarizer

        Args:
            ollama_endpoint: Ollama API endpoint
            ollama_model: Model to use for summarization
            timeout: Request timeout in seconds
        """
        self.ollama_endpoint = ollama_endpoint
        self.ollama_model = ollama_model
        self.timeout = timeout

        logger.info(
            f"Summarizer initialized: "
            f"endpoint={ollama_endpoint}, model={ollama_model}"
        )

    def summarize_messages(
        self,
        messages: List[Dict[str, Any]],
        target_tokens: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate a summary of messages

        Args:
            messages: List of messages to summarize
            target_tokens: Target token count for summary
            metadata: Optional metadata about the messages

        Returns:
            Summary text
        """
        logger.info(
            f"Generating summary for {len(messages)} messages "
            f"(target: {target_tokens} tokens)"
        )

        # Build context for summarization
        context = self._build_summary_context(messages, metadata)

        # Create summarization prompt
        prompt = self._create_summary_prompt(context, target_tokens)

        try:
            # Call Ollama
            summary = self._call_ollama(prompt, target_tokens)

            logger.info(f"Generated summary (~{len(summary) // 4} tokens)")
            return summary

        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            # Fallback to simple summary
            return self._fallback_summary(messages, metadata)

    def _build_summary_context(
        self,
        messages: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build context string from messages"""
        context_parts = []

        # Add metadata context if available
        if metadata:
            context_parts.append("## Context Metadata")

            if metadata.get("file_paths"):
                context_parts.append(
                    f"Files involved: {', '.join(metadata['file_paths'][:10])}"
                )

            if metadata.get("tools_used"):
                context_parts.append(
                    f"Tools used: {', '.join(metadata['tools_used'])}"
                )

            if metadata.get("timestamp_range"):
                ts_range = metadata["timestamp_range"]
                if ts_range.get("start") and ts_range.get("end"):
                    context_parts.append(
                        f"Time range: {ts_range['start']} to {ts_range['end']}"
                    )

            context_parts.append("")

        # Add messages
        context_parts.append("## Conversation")

        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            # Format content
            if isinstance(content, str):
                content_str = content
            elif isinstance(content, list):
                # Extract text from content blocks
                content_str = self._extract_text_from_blocks(content)
            else:
                content_str = str(content)

            # Truncate very long messages
            if len(content_str) > 1000:
                content_str = content_str[:1000] + "... [truncated]"

            context_parts.append(f"### Message {i+1} ({role})")
            context_parts.append(content_str)
            context_parts.append("")

        return "\n".join(context_parts)

    def _extract_text_from_blocks(self, blocks: List[Dict[str, Any]]) -> str:
        """Extract text from content blocks"""
        text_parts = []

        for block in blocks:
            if not isinstance(block, dict):
                text_parts.append(str(block))
                continue

            block_type = block.get("type", "text")

            if block_type == "text":
                text_parts.append(block.get("text", ""))

            elif block_type == "tool_use":
                tool_name = block.get("name", "unknown")
                tool_input = block.get("input", {})
                text_parts.append(
                    f"[Tool: {tool_name} with input: {json.dumps(tool_input)}]"
                )

            elif block_type == "tool_result":
                result = block.get("content", "")
                if isinstance(result, list):
                    result = self._extract_text_from_blocks(result)
                text_parts.append(f"[Tool Result: {result}]")

            elif block_type == "image":
                text_parts.append("[Image attached]")

        return "\n".join(text_parts)

    def _create_summary_prompt(
        self,
        context: str,
        target_tokens: int
    ) -> str:
        """Create prompt for summarization"""
        return f"""You are a conversation summarizer. Your task is to create a concise summary of the following conversation context.

IMPORTANT REQUIREMENTS:
1. The summary should be approximately {target_tokens} tokens ({target_tokens * 4} characters)
2. Focus on preserving key information that might be referenced later:
   - Important decisions made
   - Files created, modified, or discussed
   - Bug fixes and solutions
   - Configuration changes
   - Key context that affects subsequent conversation
3. Use clear, structured format
4. Be factual and precise
5. Include specific details like file paths, function names, error messages
6. Omit pleasantries and redundant confirmations

CONVERSATION CONTEXT TO SUMMARIZE:

{context}

SUMMARY (approximately {target_tokens} tokens):"""

    def _call_ollama(self, prompt: str, max_tokens: int) -> str:
        """Call Ollama API for summarization"""
        request_data = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,  # Lower temperature for more focused summaries
                "num_predict": max_tokens * 2  # Allow some flexibility
            }
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.ollama_endpoint}/api/generate",
                json=request_data
            )
            response.raise_for_status()

            result = response.json()
            summary = result.get("response", "")

            return summary.strip()

    def _fallback_summary(
        self,
        messages: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate a simple fallback summary without LLM"""
        summary_parts = [
            f"[ARCHIVED: {len(messages)} messages]",
            ""
        ]

        if metadata:
            if metadata.get("file_paths"):
                files = metadata["file_paths"][:5]
                summary_parts.append(f"Files: {', '.join(files)}")

            if metadata.get("tools_used"):
                tools = metadata["tools_used"]
                summary_parts.append(f"Tools: {', '.join(tools)}")

            if metadata.get("timestamp_range"):
                ts_range = metadata["timestamp_range"]
                if ts_range.get("start"):
                    summary_parts.append(f"Period: {ts_range['start']} to {ts_range.get('end', 'now')}")

        # Add snippet from first and last messages
        if messages:
            first_content = str(messages[0].get("content", ""))[:100]
            summary_parts.append(f"\nFirst message: {first_content}...")

            if len(messages) > 1:
                last_content = str(messages[-1].get("content", ""))[:100]
                summary_parts.append(f"Last message: {last_content}...")

        summary_parts.append("\n[Full context archived - can be retrieved if referenced]")

        return "\n".join(summary_parts)

    def generate_enhanced_summary(
        self,
        messages: List[Dict[str, Any]],
        target_tokens: int,
        metadata: Optional[Dict[str, Any]] = None,
        include_index: bool = True
    ) -> Dict[str, Any]:
        """
        Generate enhanced summary with indexing information

        Args:
            messages: Messages to summarize
            target_tokens: Target summary length
            metadata: Message metadata
            include_index: Whether to generate index data

        Returns:
            Dictionary with summary and index data
        """
        # Generate main summary
        summary_text = self.summarize_messages(messages, target_tokens, metadata)

        result = {
            "summary": summary_text,
            "original_message_count": len(messages),
            "estimated_summary_tokens": len(summary_text) // 4
        }

        if include_index:
            # Extract keywords and file paths for indexing
            result["index_data"] = {
                "keywords": self._extract_keywords(messages),
                "file_paths": metadata.get("file_paths", []) if metadata else [],
                "tools_used": metadata.get("tools_used", []) if metadata else []
            }

        return result

    def _extract_keywords(
        self,
        messages: List[Dict[str, Any]],
        max_keywords: int = 20
    ) -> List[str]:
        """
        Extract keywords from messages for indexing

        Simple keyword extraction - could be enhanced with NLP
        """
        keywords = set()

        # Common code-related keywords to look for
        code_patterns = [
            "function", "class", "method", "variable", "error", "bug",
            "fix", "implement", "create", "update", "delete", "modify",
            "test", "debug", "refactor", "optimize"
        ]

        for msg in messages:
            content = str(msg.get("content", "")).lower()

            # Add code patterns found
            for pattern in code_patterns:
                if pattern in content:
                    keywords.add(pattern)

            # Extract potential identifiers (simple approach)
            import re
            identifiers = re.findall(r'\b[a-z_][a-z0-9_]{2,}\b', content)
            keywords.update(identifiers[:5])  # Add up to 5 per message

        # Return most common keywords
        return list(keywords)[:max_keywords]
