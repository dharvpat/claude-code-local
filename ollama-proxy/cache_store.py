"""
Cache Storage Layer
Handles persistent storage of sessions, archives, and indexes
"""

import os
import json
import sqlite3
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class CacheStore:
    """Persistent cache storage using SQLite and JSON files"""

    def __init__(self, cache_dir: str = "./cache"):
        self.cache_dir = Path(cache_dir)
        self.sessions_dir = self.cache_dir / "sessions"
        self.archives_dir = self.cache_dir / "archives"
        self.index_dir = self.cache_dir / "index"

        # Create directories
        self.cache_dir.mkdir(exist_ok=True)
        self.sessions_dir.mkdir(exist_ok=True)
        self.archives_dir.mkdir(exist_ok=True)
        self.index_dir.mkdir(exist_ok=True)

        # Initialize database
        self.db_path = self.cache_dir / "sessions.db"
        self._init_database()

        logger.info(f"CacheStore initialized at {self.cache_dir}")

    def _init_database(self):
        """Initialize SQLite database schema"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_messages INTEGER DEFAULT 0,
                    active_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    archive_count INTEGER DEFAULT 0,
                    metadata TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS archives (
                    archive_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message_range TEXT,
                    original_tokens INTEGER,
                    summary_tokens INTEGER,
                    content_hash TEXT,
                    metadata TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS content_index (
                    content_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    archive_id TEXT,
                    content_type TEXT,
                    keywords TEXT,
                    file_paths TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
                    FOREIGN KEY (archive_id) REFERENCES archives(archive_id)
                )
            """)

            # Create indexes for faster queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session_accessed ON sessions(last_accessed)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_archive_session ON archives(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_content_session ON content_index(session_id)")

            conn.commit()

        logger.debug("Database initialized")

    def create_session(self, session_id: str, metadata: Optional[Dict] = None) -> bool:
        """Create a new session"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO sessions (session_id, metadata) VALUES (?, ?)",
                    (session_id, json.dumps(metadata or {}))
                )
                conn.commit()

            # Create empty session file
            session_file = self.sessions_dir / f"{session_id}.json"
            session_data = {
                "session_id": session_id,
                "created_at": datetime.now().isoformat(),
                "messages": [],
                "metadata": metadata or {}
            }
            session_file.write_text(json.dumps(session_data, indent=2))

            logger.info(f"Created session: {session_id}")
            return True

        except sqlite3.IntegrityError:
            logger.warning(f"Session already exists: {session_id}")
            return False
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            return False

    def session_exists(self, session_id: str) -> bool:
        """Check if session exists"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?",
                (session_id,)
            )
            return cursor.fetchone() is not None

    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load session data from disk"""
        session_file = self.sessions_dir / f"{session_id}.json"

        if not session_file.exists():
            logger.warning(f"Session file not found: {session_id}")
            return None

        try:
            session_data = json.loads(session_file.read_text())

            # Update last accessed timestamp
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE sessions SET last_accessed = CURRENT_TIMESTAMP WHERE session_id = ?",
                    (session_id,)
                )
                conn.commit()

            logger.debug(f"Loaded session: {session_id}")
            return session_data

        except Exception as e:
            logger.error(f"Error loading session: {e}")
            return None

    def save_session(self, session_id: str, session_data: Dict[str, Any]) -> bool:
        """Save session data to disk"""
        session_file = self.sessions_dir / f"{session_id}.json"

        try:
            session_file.write_text(json.dumps(session_data, indent=2))

            # Update metadata in database
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE sessions
                    SET last_accessed = CURRENT_TIMESTAMP,
                        total_messages = ?,
                        active_tokens = ?,
                        total_tokens = ?
                    WHERE session_id = ?
                """, (
                    len(session_data.get("messages", [])),
                    session_data.get("active_tokens", 0),
                    session_data.get("total_tokens", 0),
                    session_id
                ))
                conn.commit()

            logger.debug(f"Saved session: {session_id}")
            return True

        except Exception as e:
            logger.error(f"Error saving session: {e}")
            return False

    def create_archive(
        self,
        session_id: str,
        messages: List[Dict],
        summary: str,
        original_tokens: int,
        summary_tokens: int,
        metadata: Optional[Dict] = None
    ) -> str:
        """Create an archive of old context"""
        # Generate archive ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        content_hash = hashlib.sha256(json.dumps(messages).encode()).hexdigest()[:8]
        archive_id = f"{session_id}_archive_{timestamp}_{content_hash}"

        try:
            # Save archive data to file
            archive_file = self.archives_dir / f"{archive_id}.json"
            archive_data = {
                "archive_id": archive_id,
                "session_id": session_id,
                "created_at": datetime.now().isoformat(),
                "messages": messages,
                "summary": summary,
                "original_tokens": original_tokens,
                "summary_tokens": summary_tokens,
                "metadata": metadata or {}
            }
            archive_file.write_text(json.dumps(archive_data, indent=2))

            # Record in database
            with sqlite3.connect(self.db_path) as conn:
                message_range = f"{0}-{len(messages)}"
                conn.execute("""
                    INSERT INTO archives (
                        archive_id, session_id, message_range,
                        original_tokens, summary_tokens, content_hash, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    archive_id, session_id, message_range,
                    original_tokens, summary_tokens, content_hash,
                    json.dumps(metadata or {})
                ))

                # Update session archive count
                conn.execute("""
                    UPDATE sessions
                    SET archive_count = archive_count + 1
                    WHERE session_id = ?
                """, (session_id,))

                conn.commit()

            logger.info(f"Created archive: {archive_id}")
            return archive_id

        except Exception as e:
            logger.error(f"Error creating archive: {e}")
            raise

    def load_archive(self, archive_id: str) -> Optional[Dict[str, Any]]:
        """Load archive data from disk"""
        archive_file = self.archives_dir / f"{archive_id}.json"

        if not archive_file.exists():
            logger.warning(f"Archive file not found: {archive_id}")
            return None

        try:
            return json.loads(archive_file.read_text())
        except Exception as e:
            logger.error(f"Error loading archive: {e}")
            return None

    def get_session_archives(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all archives for a session"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM archives
                WHERE session_id = ?
                ORDER BY created_at DESC
            """, (session_id,))

            archives = []
            for row in cursor.fetchall():
                archives.append(dict(row))

            return archives

    def index_content(
        self,
        session_id: str,
        archive_id: str,
        content_type: str,
        keywords: List[str],
        file_paths: List[str]
    ) -> bool:
        """Index content for retrieval"""
        try:
            content_id = f"{archive_id}_{content_type}_{hashlib.sha256(''.join(keywords).encode()).hexdigest()[:8]}"

            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO content_index (
                        content_id, session_id, archive_id,
                        content_type, keywords, file_paths
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    content_id, session_id, archive_id,
                    content_type,
                    json.dumps(keywords),
                    json.dumps(file_paths)
                ))
                conn.commit()

            logger.debug(f"Indexed content: {content_id}")
            return True

        except Exception as e:
            logger.error(f"Error indexing content: {e}")
            return False

    def search_content(
        self,
        session_id: str,
        keywords: Optional[List[str]] = None,
        file_paths: Optional[List[str]] = None
    ) -> List[str]:
        """Search for archived content by keywords or file paths"""
        archive_ids = set()

        try:
            with sqlite3.connect(self.db_path) as conn:
                if keywords:
                    # Search by keywords
                    for keyword in keywords:
                        cursor = conn.execute("""
                            SELECT DISTINCT archive_id FROM content_index
                            WHERE session_id = ? AND keywords LIKE ?
                        """, (session_id, f'%{keyword}%'))

                        for row in cursor.fetchall():
                            archive_ids.add(row[0])

                if file_paths:
                    # Search by file paths
                    for path in file_paths:
                        cursor = conn.execute("""
                            SELECT DISTINCT archive_id FROM content_index
                            WHERE session_id = ? AND file_paths LIKE ?
                        """, (session_id, f'%{path}%'))

                        for row in cursor.fetchall():
                            archive_ids.add(row[0])

            return list(archive_ids)

        except Exception as e:
            logger.error(f"Error searching content: {e}")
            return []

    def get_session_stats(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a session"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,)
            )

            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def list_sessions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all sessions"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM sessions
                ORDER BY last_accessed DESC
                LIMIT ?
            """, (limit,))

            return [dict(row) for row in cursor.fetchall()]

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and its archives"""
        try:
            # Get all archives for this session
            archives = self.get_session_archives(session_id)

            # Delete archive files
            for archive in archives:
                archive_file = self.archives_dir / f"{archive['archive_id']}.json"
                if archive_file.exists():
                    archive_file.unlink()

            # Delete session file
            session_file = self.sessions_dir / f"{session_id}.json"
            if session_file.exists():
                session_file.unlink()

            # Delete from database
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM content_index WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM archives WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                conn.commit()

            logger.info(f"Deleted session: {session_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            return False

    def cleanup_old_sessions(self, days: int = 30) -> int:
        """Clean up sessions older than specified days"""
        cutoff_date = datetime.now() - timedelta(days=days)

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT session_id FROM sessions
                    WHERE last_accessed < ?
                """, (cutoff_date,))

                old_sessions = [row[0] for row in cursor.fetchall()]

            deleted = 0
            for session_id in old_sessions:
                if self.delete_session(session_id):
                    deleted += 1

            logger.info(f"Cleaned up {deleted} old sessions")
            return deleted

        except Exception as e:
            logger.error(f"Error cleaning up sessions: {e}")
            return 0

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get overall cache statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Session stats
                cursor = conn.execute("SELECT COUNT(*) FROM sessions")
                total_sessions = cursor.fetchone()[0]

                cursor = conn.execute("SELECT SUM(total_messages) FROM sessions")
                total_messages = cursor.fetchone()[0] or 0

                cursor = conn.execute("SELECT SUM(total_tokens) FROM sessions")
                total_tokens = cursor.fetchone()[0] or 0

                # Archive stats
                cursor = conn.execute("SELECT COUNT(*) FROM archives")
                total_archives = cursor.fetchone()[0]

                cursor = conn.execute("SELECT SUM(original_tokens) FROM archives")
                archived_tokens = cursor.fetchone()[0] or 0

            # Disk usage
            cache_size = sum(f.stat().st_size for f in self.cache_dir.rglob('*') if f.is_file())

            return {
                "total_sessions": total_sessions,
                "total_messages": total_messages,
                "total_tokens": total_tokens,
                "total_archives": total_archives,
                "archived_tokens": archived_tokens,
                "cache_size_bytes": cache_size,
                "cache_size_mb": round(cache_size / 1024 / 1024, 2)
            }

        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {}
