"""
Context Manager
Monitors token usage and manages context windows
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class ContextManager:
    """Manages context windows and token limits"""

    def __init__(
        self,
        max_active_tokens: int = 8000,
        max_total_tokens: int = 100000,
        summary_ratio: float = 0.2,
        preserve_recent: int = 5
    ):
        """
        Initialize Context Manager

        Args:
            max_active_tokens: Maximum tokens before triggering summarization
            max_total_tokens: Maximum total tokens tracked (active + archived)
            summary_ratio: Target ratio for summaries (0.2 = 20% of original)
            preserve_recent: Number of recent messages to always preserve
        """
        self.max_active_tokens = max_active_tokens
        self.max_total_tokens = max_total_tokens
        self.summary_ratio = summary_ratio
        self.preserve_recent = preserve_recent

        logger.info(
            f"ContextManager initialized: "
            f"max_active={max_active_tokens}, "
            f"max_total={max_total_tokens}, "
            f"summary_ratio={summary_ratio}"
        )

    def estimate_tokens(self, content: Any) -> int:
        """
        Estimate token count for content

        Args:
            content: Text string or content blocks

        Returns:
            Estimated token count
        """
        if isinstance(content, str):
            # Simple estimation: ~4 characters per token
            return len(content) // 4

        elif isinstance(content, list):
            # Content blocks
            total = 0
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        total += len(block.get("text", "")) // 4
                    elif block.get("type") == "image":
                        # Images take variable tokens, estimate conservatively
                        total += 1000
                    elif block.get("type") in ["tool_use", "tool_result"]:
                        total += len(str(block)) // 4
                else:
                    total += len(str(block)) // 4
            return total

        return len(str(content)) // 4

    def estimate_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """
        Estimate total tokens for a list of messages

        Args:
            messages: List of message dictionaries

        Returns:
            Total estimated tokens
        """
        total = 0
        for msg in messages:
            # Role overhead (~1 token)
            total += 1

            # Content
            content = msg.get("content", "")
            total += self.estimate_tokens(content)

            # Metadata overhead
            if msg.get("name"):
                total += len(msg["name"]) // 4

        return total

    def should_archive(self, active_tokens: int) -> bool:
        """
        Check if context should be archived

        Args:
            active_tokens: Current active token count

        Returns:
            True if archival should be triggered
        """
        should = active_tokens >= self.max_active_tokens

        if should:
            logger.info(
                f"Archival threshold reached: "
                f"{active_tokens} >= {self.max_active_tokens}"
            )

        return should

    def calculate_archive_size(
        self,
        messages: List[Dict[str, Any]],
        active_tokens: int
    ) -> Tuple[int, int]:
        """
        Calculate how many messages to archive

        Args:
            messages: List of all messages
            active_tokens: Current active token count

        Returns:
            tuple: (num_messages_to_archive, estimated_tokens_to_archive)
        """
        if active_tokens < self.max_active_tokens:
            return 0, 0

        # Target: reduce active tokens to ~50% of max
        target_tokens = int(self.max_active_tokens * 0.5)
        tokens_to_remove = active_tokens - target_tokens

        # Preserve recent messages
        archivable_messages = messages[:-self.preserve_recent] if len(messages) > self.preserve_recent else []

        if not archivable_messages:
            logger.warning("No messages available to archive (all recent)")
            return 0, 0

        # Calculate how many messages to archive
        accumulated_tokens = 0
        num_to_archive = 0

        for msg in archivable_messages:
            msg_tokens = self.estimate_tokens(msg.get("content", ""))
            accumulated_tokens += msg_tokens
            num_to_archive += 1

            if accumulated_tokens >= tokens_to_remove:
                break

        logger.info(
            f"Archive plan: {num_to_archive} messages "
            f"(~{accumulated_tokens} tokens) from {len(messages)} total"
        )

        return num_to_archive, accumulated_tokens

    def prepare_archive_metadata(
        self,
        messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Extract metadata from messages for archival

        Args:
            messages: Messages to be archived

        Returns:
            Metadata dictionary
        """
        metadata = {
            "message_count": len(messages),
            "file_paths": set(),
            "keywords": set(),
            "tools_used": set(),
            "timestamp_range": {
                "start": None,
                "end": None
            }
        }

        for msg in messages:
            content = msg.get("content", "")

            # Extract file paths
            if isinstance(content, str):
                # Simple pattern matching for common file paths
                import re
                paths = re.findall(r'[\w/.-]+\.\w+', content)
                metadata["file_paths"].update(paths)

            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        # Tool use
                        if block.get("type") == "tool_use":
                            tool_name = block.get("name", "")
                            metadata["tools_used"].add(tool_name)

                            # Extract file paths from tool input
                            tool_input = block.get("input", {})
                            if "file_path" in tool_input:
                                metadata["file_paths"].add(tool_input["file_path"])

                        # Tool result might contain file references
                        elif block.get("type") == "tool_result":
                            result_content = str(block.get("content", ""))
                            import re
                            paths = re.findall(r'[\w/.-]+\.\w+', result_content)
                            metadata["file_paths"].update(paths)

            # Timestamps
            if "timestamp" in msg:
                ts = msg["timestamp"]
                if not metadata["timestamp_range"]["start"]:
                    metadata["timestamp_range"]["start"] = ts
                metadata["timestamp_range"]["end"] = ts

        # Convert sets to lists for JSON serialization
        metadata["file_paths"] = list(metadata["file_paths"])
        metadata["keywords"] = list(metadata["keywords"])
        metadata["tools_used"] = list(metadata["tools_used"])

        return metadata

    def validate_context_size(
        self,
        active_tokens: int,
        total_tokens: int
    ) -> Dict[str, Any]:
        """
        Validate context size against limits

        Args:
            active_tokens: Current active tokens
            total_tokens: Total tokens (active + archived)

        Returns:
            Validation result with status and recommendations
        """
        result = {
            "valid": True,
            "warnings": [],
            "recommendations": []
        }

        # Check active tokens
        if active_tokens > self.max_active_tokens:
            result["warnings"].append(
                f"Active tokens ({active_tokens}) exceeds limit ({self.max_active_tokens})"
            )
            result["recommendations"].append("Trigger archival")
            result["valid"] = False

        elif active_tokens > self.max_active_tokens * 0.8:
            result["warnings"].append(
                f"Active tokens ({active_tokens}) at 80% of limit"
            )
            result["recommendations"].append("Consider archival soon")

        # Check total tokens
        if total_tokens > self.max_total_tokens:
            result["warnings"].append(
                f"Total tokens ({total_tokens}) exceeds limit ({self.max_total_tokens})"
            )
            result["recommendations"].append("Delete old archives or start new session")
            result["valid"] = False

        elif total_tokens > self.max_total_tokens * 0.9:
            result["warnings"].append(
                f"Total tokens ({total_tokens}) at 90% of limit"
            )
            result["recommendations"].append("Consider cleaning up old archives")

        return result

    def calculate_summary_target(self, original_tokens: int) -> int:
        """
        Calculate target token count for summary

        Args:
            original_tokens: Original token count

        Returns:
            Target token count for summary
        """
        target = int(original_tokens * self.summary_ratio)

        # Ensure minimum summary size
        min_summary = 100
        max_summary = 2000

        return max(min_summary, min(target, max_summary))

    def merge_contexts(
        self,
        base_messages: List[Dict[str, Any]],
        additional_context: List[Dict[str, Any]],
        max_tokens: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Merge additional context into base messages

        Args:
            base_messages: Base conversation messages
            additional_context: Additional context to inject
            max_tokens: Optional token limit for merged context

        Returns:
            Merged message list
        """
        merged = list(base_messages)

        # Insert additional context at the beginning (after system prompt if exists)
        insert_index = 0
        if merged and merged[0].get("role") == "system":
            insert_index = 1

        merged[insert_index:insert_index] = additional_context

        # Trim if needed
        if max_tokens:
            current_tokens = self.estimate_messages_tokens(merged)

            if current_tokens > max_tokens:
                logger.warning(
                    f"Merged context ({current_tokens} tokens) exceeds limit ({max_tokens})"
                )

                # Remove oldest non-system messages until under limit
                while current_tokens > max_tokens and len(merged) > 1:
                    # Find first non-system message
                    for i, msg in enumerate(merged):
                        if msg.get("role") != "system":
                            removed = merged.pop(i)
                            current_tokens -= self.estimate_tokens(removed.get("content", ""))
                            break

        return merged

    def get_context_summary(
        self,
        active_tokens: int,
        total_tokens: int,
        message_count: int,
        archive_count: int
    ) -> Dict[str, Any]:
        """
        Get summary of current context state

        Args:
            active_tokens: Current active tokens
            total_tokens: Total tokens
            message_count: Number of active messages
            archive_count: Number of archives

        Returns:
            Context summary
        """
        active_percentage = (active_tokens / self.max_active_tokens) * 100
        total_percentage = (total_tokens / self.max_total_tokens) * 100

        return {
            "active_tokens": active_tokens,
            "active_limit": self.max_active_tokens,
            "active_percentage": round(active_percentage, 1),
            "total_tokens": total_tokens,
            "total_limit": self.max_total_tokens,
            "total_percentage": round(total_percentage, 1),
            "message_count": message_count,
            "archive_count": archive_count,
            "should_archive": self.should_archive(active_tokens),
            "health": self._get_health_status(active_percentage, total_percentage)
        }

    def _get_health_status(
        self,
        active_percentage: float,
        total_percentage: float
    ) -> str:
        """Get health status based on usage percentages"""
        if total_percentage > 95 or active_percentage > 95:
            return "critical"
        elif total_percentage > 80 or active_percentage > 80:
            return "warning"
        elif total_percentage > 60 or active_percentage > 60:
            return "good"
        else:
            return "healthy"
