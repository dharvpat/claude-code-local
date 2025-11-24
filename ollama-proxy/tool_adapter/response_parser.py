"""
Response Parser
Detects and extracts tool usage from model responses in various formats
"""

import json
import re
import logging
from typing import Dict, List, Any, Optional, Tuple
from .model_capabilities import ModelTier
from .format_translator import FormatTranslator

logger = logging.getLogger(__name__)


class ResponseParser:
    """Parse model responses to detect tool usage"""

    def __init__(self, enable_natural_language_detection: bool = False):
        """
        Initialize response parser

        Args:
            enable_natural_language_detection: Whether to detect tool intent
                from natural language (proactive mode)
        """
        self.translator = FormatTranslator()
        self.enable_nl_detection = enable_natural_language_detection
        logger.debug(f"ResponseParser initialized (NL detection={enable_natural_language_detection})")

    def parse_response(
        self,
        ollama_response: Dict[str, Any],
        tier: ModelTier,
        original_request: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Parse Ollama response and extract tool usage

        Args:
            ollama_response: Response from Ollama API
            tier: Model capability tier
            original_request: Original Anthropic request

        Returns:
            Tuple of (tool_use_dict or None, text_content)
        """
        # Extract message content
        message = ollama_response.get("message", {})
        content = message.get("content", "")

        # Try tier-specific parsing
        if tier == ModelTier.TIER_1_NATIVE_OPENAI:
            tool_use = self._parse_tier_1_openai(message, content)
        elif tier == ModelTier.TIER_2_PARTIAL:
            tool_use = self._parse_tier_2_partial(message, content)
        else:  # TIER_3_PROMPT_BASED
            tool_use = self._parse_tier_3_prompt_based(content)

        # Fallback: try all parsers if tier-specific failed
        if not tool_use:
            tool_use = self._try_all_parsers(message, content)

        # Optional: Natural language detection (proactive mode)
        if not tool_use and self.enable_nl_detection:
            tool_use = self.translator.detect_natural_language_tool_intent(content)
            if tool_use:
                logger.info("Detected tool usage from natural language")

        return tool_use, content

    def _parse_tier_1_openai(
        self,
        message: Dict[str, Any],
        content: str
    ) -> Optional[Dict[str, Any]]:
        """
        Parse Tier 1 (OpenAI-compatible) responses

        Look for function_call or tool_calls in the response
        """
        # Check for OpenAI function_call
        if "function_call" in message:
            logger.debug("Found function_call in response")
            return self.translator.openai_to_anthropic_tool_use(message)

        # Check for OpenAI tool_calls (newer format)
        if "tool_calls" in message and message["tool_calls"]:
            logger.debug("Found tool_calls in response")
            return self.translator.openai_to_anthropic_tool_use(message)

        return None

    def _parse_tier_2_partial(
        self,
        message: Dict[str, Any],
        content: str
    ) -> Optional[Dict[str, Any]]:
        """
        Parse Tier 2 (partial support) responses

        Try OpenAI format first, then prompt-based
        """
        # Try OpenAI format (some Tier 2 models use it)
        tool_use = self._parse_tier_1_openai(message, content)
        if tool_use:
            return tool_use

        # Try prompt-based format
        return self._parse_tier_3_prompt_based(content)

    def _parse_tier_3_prompt_based(self, content: str) -> Optional[Dict[str, Any]]:
        """
        Parse Tier 3 (prompt-based) responses

        Look for <tool>...</tool> and <input>...</input> tags
        """
        # Try standard XML-style tags
        tool_use = self.translator.prompt_based_to_anthropic_tool_use(content)
        if tool_use:
            logger.debug("Found prompt-based tool usage with XML tags")
            return tool_use

        # Try alternative formats
        tool_use = self._try_alternative_formats(content)
        if tool_use:
            return tool_use

        return None

    def _try_alternative_formats(self, content: str) -> Optional[Dict[str, Any]]:
        """
        Try parsing alternative tool formats

        Handles various ways models might express tool usage:
        - TOOL: tool_name\nINPUT: {...}
        - [TOOL] tool_name [INPUT] {...}
        - etc.
        """
        # Format 1: TOOL: name / INPUT: {...}
        pattern1 = r'TOOL:\s*(\w+)\s*(?:INPUT|PARAMETERS):\s*(\{[^}]+\})'
        match = re.search(pattern1, content, re.IGNORECASE | re.DOTALL)
        if match:
            tool_name = match.group(1)
            input_str = match.group(2)
            try:
                input_data = json.loads(input_str)
                logger.debug(f"Parsed tool from TOOL:/INPUT: format: {tool_name}")
                return {
                    "type": "tool_use",
                    "id": f"toolu_{hash(tool_name + input_str) % 100000:05d}",
                    "name": tool_name,
                    "input": input_data
                }
            except json.JSONDecodeError:
                pass

        # Format 2: [TOOL: name] [INPUT: {...}]
        pattern2 = r'\[TOOL:\s*(\w+)\]\s*\[INPUT:\s*(\{[^}]+\})\]'
        match = re.search(pattern2, content, re.IGNORECASE | re.DOTALL)
        if match:
            tool_name = match.group(1)
            input_str = match.group(2)
            try:
                input_data = json.loads(input_str)
                logger.debug(f"Parsed tool from [TOOL]/[INPUT] format: {tool_name}")
                return {
                    "type": "tool_use",
                    "id": f"toolu_{hash(tool_name + input_str) % 100000:05d}",
                    "name": tool_name,
                    "input": input_data
                }
            except json.JSONDecodeError:
                pass

        # Format 3: JSON-like function call
        pattern3 = r'\{[^}]*"function":\s*"(\w+)"[^}]*"arguments":\s*(\{[^}]+\})[^}]*\}'
        match = re.search(pattern3, content, re.DOTALL)
        if match:
            tool_name = match.group(1)
            input_str = match.group(2)
            try:
                input_data = json.loads(input_str)
                logger.debug(f"Parsed tool from JSON function format: {tool_name}")
                return {
                    "type": "tool_use",
                    "id": f"toolu_{hash(tool_name + input_str) % 100000:05d}",
                    "name": tool_name,
                    "input": input_data
                }
            except json.JSONDecodeError:
                pass

        return None

    def _try_all_parsers(
        self,
        message: Dict[str, Any],
        content: str
    ) -> Optional[Dict[str, Any]]:
        """
        Try all parsing methods as fallback

        Used when tier-specific parsing fails
        """
        # Try OpenAI format
        tool_use = self._parse_tier_1_openai(message, content)
        if tool_use:
            logger.debug("Fallback: Found tool via OpenAI parser")
            return tool_use

        # Try prompt-based
        tool_use = self._parse_tier_3_prompt_based(content)
        if tool_use:
            logger.debug("Fallback: Found tool via prompt-based parser")
            return tool_use

        return None

    def extract_text_content(self, ollama_response: Dict[str, Any]) -> str:
        """
        Extract just the text content from Ollama response

        Args:
            ollama_response: Response from Ollama

        Returns:
            Text content string
        """
        message = ollama_response.get("message", {})
        content = message.get("content", "")

        # Remove tool tags if present
        content = re.sub(r'<tool>.*?</tool>', '', content, flags=re.DOTALL)
        content = re.sub(r'<input>.*?</input>', '', content, flags=re.DOTALL)

        return content.strip()

    def has_tool_usage(self, ollama_response: Dict[str, Any], tier: ModelTier) -> bool:
        """
        Quick check if response contains tool usage

        Args:
            ollama_response: Response from Ollama
            tier: Model capability tier

        Returns:
            True if tool usage detected
        """
        message = ollama_response.get("message", {})
        content = message.get("content", "")

        # Quick checks based on tier
        if tier == ModelTier.TIER_1_NATIVE_OPENAI:
            return "function_call" in message or "tool_calls" in message

        elif tier == ModelTier.TIER_2_PARTIAL:
            return ("function_call" in message or
                    "tool_calls" in message or
                    "<tool>" in content or
                    "TOOL:" in content)

        else:  # TIER_3
            return "<tool>" in content or "TOOL:" in content

    def validate_tool_use(self, tool_use: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate a tool_use dictionary

        Args:
            tool_use: Tool use dictionary to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(tool_use, dict):
            return False, "Tool use must be a dictionary"

        if tool_use.get("type") != "tool_use":
            return False, "Missing or incorrect 'type' field"

        if not tool_use.get("name"):
            return False, "Missing 'name' field"

        if "input" not in tool_use:
            return False, "Missing 'input' field"

        if not isinstance(tool_use.get("input"), dict):
            return False, "'input' must be a dictionary"

        return True, None

    def clean_tool_response_text(self, text: str) -> str:
        """
        Clean text content that may contain tool usage artifacts

        Removes tool tags and formatting from mixed responses
        """
        # Remove XML-style tool tags
        text = re.sub(r'<tool>.*?</tool>', '', text, flags=re.DOTALL)
        text = re.sub(r'<input>.*?</input>', '', text, flags=re.DOTALL)

        # Remove TOOL:/INPUT: format
        text = re.sub(r'TOOL:\s*\w+\s*INPUT:\s*\{[^}]+\}', '', text, flags=re.IGNORECASE | re.DOTALL)

        # Remove bracket format
        text = re.sub(r'\[TOOL:.*?\]\s*\[INPUT:.*?\]', '', text, flags=re.IGNORECASE | re.DOTALL)

        # Clean up extra whitespace
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
        text = text.strip()

        return text

    def get_parsing_stats(self) -> Dict[str, int]:
        """
        Get statistics about parsing operations

        Returns:
            Dictionary with parsing statistics
        """
        # This is a placeholder - in a production system you'd track these
        return {
            "total_parses": 0,
            "openai_format": 0,
            "prompt_based": 0,
            "natural_language": 0,
            "failures": 0
        }
