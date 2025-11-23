"""
Context Retrieval System
Intelligently loads archived context when referenced
"""

import re
import logging
from typing import List, Dict, Any, Optional, Set
from cache_store import CacheStore

logger = logging.getLogger(__name__)


class ContextRetrieval:
    """Smart context retrieval from archives"""

    def __init__(
        self,
        cache_store: CacheStore,
        enabled: bool = True,
        similarity_threshold: float = 0.6
    ):
        """
        Initialize Context Retrieval

        Args:
            cache_store: Cache storage instance
            enabled: Whether retrieval is enabled
            similarity_threshold: Threshold for relevance matching
        """
        self.cache_store = cache_store
        self.enabled = enabled
        self.similarity_threshold = similarity_threshold

        # Reference patterns
        self.temporal_patterns = [
            r'\b(earlier|before|previously|ago|past|last time|remember when)\b',
            r'\b(that|the) (\w+ ){0,3}(we|I) (did|fixed|changed|created|discussed)\b'
        ]

        self.file_patterns = [
            r'[\w/.-]+\.\w+',  # File paths
            r'\b[\w_]+\.py\b',  # Python files
            r'\b[\w_]+\.js\b',  # JS files
            r'\b[\w_]+\.ts\b',  # TS files
        ]

        logger.info(
            f"ContextRetrieval initialized: "
            f"enabled={enabled}, threshold={similarity_threshold}"
        )

    def analyze_message(self, message: str) -> Dict[str, Any]:
        """
        Analyze message for references to past context

        Args:
            message: User message

        Returns:
            Analysis dict with detected references
        """
        analysis = {
            "has_temporal_reference": False,
            "has_file_reference": False,
            "has_code_reference": False,
            "temporal_keywords": [],
            "file_paths": [],
            "code_elements": [],
            "keywords": [],
            "should_retrieve": False
        }

        message_lower = message.lower()

        # Check for temporal references
        for pattern in self.temporal_patterns:
            matches = re.findall(pattern, message_lower, re.IGNORECASE)
            if matches:
                analysis["has_temporal_reference"] = True
                analysis["temporal_keywords"].extend([m if isinstance(m, str) else m[0] for m in matches])

        # Check for file references
        for pattern in self.file_patterns:
            matches = re.findall(pattern, message)
            if matches:
                analysis["has_file_reference"] = True
                analysis["file_paths"].extend(matches)

        # Check for code element references
        code_patterns = [
            r'\b(function|class|method|variable)\s+(\w+)',
            r'\b(\w+)\s+(function|class|method)',
            r'`(\w+)`'  # Code in backticks
        ]

        for pattern in code_patterns:
            matches = re.findall(pattern, message)
            if matches:
                analysis["has_code_reference"] = True
                for match in matches:
                    if isinstance(match, tuple):
                        analysis["code_elements"].extend([m for m in match if m not in ['function', 'class', 'method', 'variable']])
                    else:
                        analysis["code_elements"].append(match)

        # Extract general keywords
        analysis["keywords"] = self._extract_keywords(message)

        # Decide if we should retrieve
        analysis["should_retrieve"] = (
            analysis["has_temporal_reference"] or
            (analysis["has_file_reference"] and analysis["has_temporal_reference"]) or
            (analysis["has_code_reference"] and len(analysis["code_elements"]) > 2)
        )

        if analysis["should_retrieve"]:
            logger.info(
                f"Detected reference to past context: "
                f"temporal={analysis['has_temporal_reference']}, "
                f"files={len(analysis['file_paths'])}, "
                f"code={len(analysis['code_elements'])}"
            )

        return analysis

    def retrieve_relevant_context(
        self,
        session_id: str,
        message: str,
        max_archives: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant archived context

        Args:
            session_id: Session ID
            message: Current message
            max_archives: Maximum number of archives to retrieve

        Returns:
            List of relevant context messages
        """
        if not self.enabled:
            return []

        # Analyze message
        analysis = self.analyze_message(message)

        if not analysis["should_retrieve"]:
            return []

        logger.info(f"Retrieving context for session {session_id}")

        # Search for relevant archives
        archive_ids = set()

        # Search by file paths
        if analysis["file_paths"]:
            file_archives = self.cache_store.search_content(
                session_id=session_id,
                file_paths=analysis["file_paths"]
            )
            archive_ids.update(file_archives)
            logger.debug(f"Found {len(file_archives)} archives by file paths")

        # Search by keywords
        search_keywords = (
            analysis["keywords"][:10] +
            analysis["code_elements"] +
            analysis["file_paths"]
        )

        if search_keywords:
            keyword_archives = self.cache_store.search_content(
                session_id=session_id,
                keywords=search_keywords
            )
            archive_ids.update(keyword_archives)
            logger.debug(f"Found {len(keyword_archives)} archives by keywords")

        if not archive_ids:
            logger.info("No relevant archives found")
            return []

        # Load and score archives
        scored_archives = []

        for archive_id in archive_ids:
            archive = self.cache_store.load_archive(archive_id)

            if not archive:
                continue

            # Score relevance
            score = self._score_archive_relevance(archive, analysis)

            if score >= self.similarity_threshold:
                scored_archives.append({
                    "archive": archive,
                    "score": score
                })

        # Sort by score and limit
        scored_archives.sort(key=lambda x: x["score"], reverse=True)
        top_archives = scored_archives[:max_archives]

        logger.info(
            f"Retrieved {len(top_archives)} relevant archives "
            f"(scores: {[round(a['score'], 2) for a in top_archives]})"
        )

        # Extract messages from archives
        retrieved_messages = []

        for item in top_archives:
            archive = item["archive"]

            # Add archive summary as a message
            summary_message = {
                "role": "system",
                "content": f"[RETRIEVED ARCHIVED CONTEXT - {archive['archive_id']}]\n\n{archive.get('summary', '')}",
                "retrieved": True,
                "archive_id": archive["archive_id"],
                "relevance_score": item["score"]
            }

            retrieved_messages.append(summary_message)

        return retrieved_messages

    def _score_archive_relevance(
        self,
        archive: Dict[str, Any],
        analysis: Dict[str, Any]
    ) -> float:
        """
        Score how relevant an archive is to the current query

        Args:
            archive: Archive data
            analysis: Message analysis

        Returns:
            Relevance score (0.0 to 1.0)
        """
        score = 0.0
        factors = 0

        # Check metadata
        metadata = archive.get("metadata", {})

        # File path matching
        if analysis["file_paths"] and metadata.get("file_paths"):
            archive_files = set(metadata["file_paths"])
            query_files = set(analysis["file_paths"])
            overlap = len(archive_files.intersection(query_files))

            if overlap > 0:
                file_score = min(1.0, overlap / len(query_files))
                score += file_score
                factors += 1
                logger.debug(f"File overlap score: {file_score}")

        # Keyword matching
        if analysis["keywords"]:
            # Check against summary
            summary = archive.get("summary", "").lower()
            keyword_matches = sum(
                1 for kw in analysis["keywords"]
                if kw.lower() in summary
            )

            if keyword_matches > 0:
                keyword_score = min(1.0, keyword_matches / len(analysis["keywords"]))
                score += keyword_score
                factors += 1
                logger.debug(f"Keyword score: {keyword_score}")

        # Code element matching
        if analysis["code_elements"]:
            summary = archive.get("summary", "").lower()
            code_matches = sum(
                1 for elem in analysis["code_elements"]
                if elem.lower() in summary
            )

            if code_matches > 0:
                code_score = min(1.0, code_matches / len(analysis["code_elements"]))
                score += code_score
                factors += 1
                logger.debug(f"Code element score: {code_score}")

        # Tool usage matching
        if metadata.get("tools_used"):
            # Bonus for archives with tool usage (more likely to be important)
            score += 0.2
            factors += 1

        # Calculate average score
        if factors > 0:
            final_score = score / factors
        else:
            final_score = 0.0

        return final_score

    def _extract_keywords(
        self,
        text: str,
        min_length: int = 3,
        max_keywords: int = 10
    ) -> List[str]:
        """Extract keywords from text"""
        # Remove common words
        stop_words = {
            'the', 'is', 'at', 'which', 'on', 'and', 'or', 'but', 'in',
            'with', 'to', 'for', 'of', 'as', 'by', 'from', 'that', 'this',
            'it', 'we', 'you', 'can', 'could', 'would', 'should', 'will',
            'what', 'where', 'when', 'why', 'how', 'please', 'thanks'
        }

        # Extract words
        words = re.findall(r'\b[a-z_][a-z0-9_]+\b', text.lower())

        # Filter and count
        keywords = [
            word for word in words
            if len(word) >= min_length and word not in stop_words
        ]

        # Get unique keywords, preserving order
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)

        return unique_keywords[:max_keywords]

    def get_full_archive_content(
        self,
        archive_id: str
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get full content from an archive

        Args:
            archive_id: Archive ID

        Returns:
            Full message list from archive
        """
        archive = self.cache_store.load_archive(archive_id)

        if not archive:
            logger.warning(f"Archive not found: {archive_id}")
            return None

        return archive.get("messages", [])

    def suggest_archives(
        self,
        session_id: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Suggest potentially useful archives for a session

        Args:
            session_id: Session ID
            limit: Maximum suggestions

        Returns:
            List of archive suggestions with metadata
        """
        archives = self.cache_store.get_session_archives(session_id)

        suggestions = []

        for archive in archives[:limit]:
            archive_data = self.cache_store.load_archive(archive["archive_id"])

            if not archive_data:
                continue

            suggestion = {
                "archive_id": archive["archive_id"],
                "created_at": archive["created_at"],
                "original_tokens": archive["original_tokens"],
                "summary_tokens": archive["summary_tokens"],
                "summary_preview": archive_data.get("summary", "")[:200] + "...",
                "metadata": archive_data.get("metadata", {})
            }

            suggestions.append(suggestion)

        return suggestions
