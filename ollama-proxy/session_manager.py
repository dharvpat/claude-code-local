"""
Session Manager
Handles session lifecycle, creation, and management
"""

import uuid
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from cache_store import CacheStore

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages conversation sessions"""

    def __init__(self, cache_store: CacheStore, auto_create: bool = True):
        self.cache_store = cache_store
        self.auto_create = auto_create
        self._active_sessions: Dict[str, Dict[str, Any]] = {}

        logger.info("SessionManager initialized")

    def get_or_create_session(
        self,
        session_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> tuple[str, Dict[str, Any]]:
        """
        Get existing session or create new one

        Returns:
            tuple: (session_id, session_data)
        """
        # Generate session ID if not provided
        if not session_id:
            if not self.auto_create:
                raise ValueError("Session ID required when auto_create is False")
            session_id = self._generate_session_id()
            logger.info(f"Generated new session ID: {session_id}")

        # Check if session exists in memory
        if session_id in self._active_sessions:
            logger.debug(f"Loaded session from memory: {session_id}")
            return session_id, self._active_sessions[session_id]

        # Try to load from disk
        session_data = self.cache_store.load_session(session_id)

        if session_data:
            # Load existing session
            self._active_sessions[session_id] = session_data
            logger.info(f"Loaded session from disk: {session_id}")
            return session_id, session_data

        # Create new session
        if self.auto_create:
            session_data = self._create_new_session(session_id, metadata)
            self._active_sessions[session_id] = session_data
            logger.info(f"Created new session: {session_id}")
            return session_id, session_data

        raise ValueError(f"Session not found: {session_id}")

    def _generate_session_id(self) -> str:
        """Generate unique session ID"""
        return f"sess_{uuid.uuid4().hex[:16]}"

    def _create_new_session(
        self,
        session_id: str,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Create a new session"""
        session_data = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "messages": [],
            "active_tokens": 0,
            "total_tokens": 0,
            "archive_ids": [],
            "metadata": metadata or {}
        }

        # Persist to disk
        self.cache_store.create_session(session_id, metadata)

        return session_data

    def add_messages(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        tokens: int
    ) -> bool:
        """Add messages to a session"""
        try:
            session_data = self._active_sessions.get(session_id)

            if not session_data:
                logger.error(f"Session not found in memory: {session_id}")
                return False

            # Add messages
            session_data["messages"].extend(messages)
            session_data["active_tokens"] += tokens
            session_data["total_tokens"] += tokens
            session_data["last_updated"] = datetime.now().isoformat()

            # Persist to disk
            self.cache_store.save_session(session_id, session_data)

            logger.debug(f"Added {len(messages)} messages to session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Error adding messages: {e}")
            return False

    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get messages from a session"""
        session_data = self._active_sessions.get(session_id)

        if not session_data:
            logger.warning(f"Session not found: {session_id}")
            return []

        messages = session_data.get("messages", [])

        if limit:
            return messages[-limit:]

        return messages

    def update_session(
        self,
        session_id: str,
        session_data: Dict[str, Any]
    ) -> bool:
        """Update session data"""
        try:
            session_data["last_updated"] = datetime.now().isoformat()

            # Update memory
            self._active_sessions[session_id] = session_data

            # Persist to disk
            self.cache_store.save_session(session_id, session_data)

            logger.debug(f"Updated session: {session_id}")
            return True

        except Exception as e:
            logger.error(f"Error updating session: {e}")
            return False

    def archive_messages(
        self,
        session_id: str,
        archive_id: str,
        num_messages: int,
        summary: str,
        summary_tokens: int
    ) -> bool:
        """
        Mark messages as archived and replace with summary

        Args:
            session_id: Session ID
            archive_id: Archive ID
            num_messages: Number of messages to archive
            summary: Summary text
            summary_tokens: Token count of summary
        """
        try:
            session_data = self._active_sessions.get(session_id)

            if not session_data:
                logger.error(f"Session not found: {session_id}")
                return False

            # Record archive ID
            if "archive_ids" not in session_data:
                session_data["archive_ids"] = []
            session_data["archive_ids"].append(archive_id)

            # Remove archived messages
            archived_messages = session_data["messages"][:num_messages]
            session_data["messages"] = session_data["messages"][num_messages:]

            # Calculate tokens saved
            archived_tokens = sum(
                self._estimate_tokens(msg.get("content", ""))
                for msg in archived_messages
            )

            # Add summary as a system message
            summary_message = {
                "role": "system",
                "content": f"[ARCHIVED CONTEXT - {archive_id}]\n\n{summary}",
                "archived": True,
                "archive_id": archive_id,
                "timestamp": datetime.now().isoformat()
            }
            session_data["messages"].insert(0, summary_message)

            # Update token counts
            session_data["active_tokens"] = session_data["active_tokens"] - archived_tokens + summary_tokens

            # Persist
            self.update_session(session_id, session_data)

            logger.info(
                f"Archived {num_messages} messages ({archived_tokens} tokens) "
                f"to {archive_id}, replaced with summary ({summary_tokens} tokens)"
            )

            return True

        except Exception as e:
            logger.error(f"Error archiving messages: {e}")
            return False

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars ≈ 1 token)"""
        if isinstance(text, list):
            # Content blocks
            total = 0
            for block in text:
                if isinstance(block, dict):
                    total += len(str(block.get("text", "")))
                else:
                    total += len(str(block))
            return total // 4
        return len(str(text)) // 4

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session information"""
        session_data = self._active_sessions.get(session_id)

        if not session_data:
            # Try loading from disk
            session_data = self.cache_store.load_session(session_id)

        if not session_data:
            return None

        return {
            "session_id": session_id,
            "created_at": session_data.get("created_at"),
            "last_updated": session_data.get("last_updated"),
            "message_count": len(session_data.get("messages", [])),
            "active_tokens": session_data.get("active_tokens", 0),
            "total_tokens": session_data.get("total_tokens", 0),
            "archive_count": len(session_data.get("archive_ids", [])),
            "metadata": session_data.get("metadata", {})
        }

    def list_sessions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all sessions"""
        sessions = self.cache_store.list_sessions(limit)

        # Enrich with memory data if available
        for session in sessions:
            session_id = session["session_id"]
            if session_id in self._active_sessions:
                memory_data = self._active_sessions[session_id]
                session["in_memory"] = True
                session["active_tokens"] = memory_data.get("active_tokens", 0)
                session["total_tokens"] = memory_data.get("total_tokens", 0)

        return sessions

    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        try:
            # Remove from memory
            if session_id in self._active_sessions:
                del self._active_sessions[session_id]

            # Delete from disk
            return self.cache_store.delete_session(session_id)

        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            return False

    def persist_all_sessions(self) -> int:
        """Persist all active sessions to disk"""
        persisted = 0

        for session_id, session_data in self._active_sessions.items():
            if self.cache_store.save_session(session_id, session_data):
                persisted += 1

        logger.info(f"Persisted {persisted} sessions to disk")
        return persisted

    def clear_memory_cache(self, session_id: Optional[str] = None):
        """Clear session from memory (but keep on disk)"""
        if session_id:
            if session_id in self._active_sessions:
                # Persist before clearing
                self.cache_store.save_session(
                    session_id,
                    self._active_sessions[session_id]
                )
                del self._active_sessions[session_id]
                logger.debug(f"Cleared session from memory: {session_id}")
        else:
            # Clear all
            self.persist_all_sessions()
            self._active_sessions.clear()
            logger.info("Cleared all sessions from memory")

    def get_stats(self) -> Dict[str, Any]:
        """Get session manager statistics"""
        cache_stats = self.cache_store.get_cache_stats()

        return {
            "active_sessions_in_memory": len(self._active_sessions),
            **cache_stats
        }
