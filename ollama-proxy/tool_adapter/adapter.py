"""
Universal Tool Adapter
Main orchestration class that makes Claude Code tools work with any Ollama model
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from .model_capabilities import ModelCapabilities, ModelTier
from .format_translator import FormatTranslator
from .prompt_generator import PromptGenerator
from .response_parser import ResponseParser

logger = logging.getLogger(__name__)


class UniversalToolAdapter:
    """
    Universal tool adapter for Ollama models

    Automatically detects model capabilities and adapts tool handling accordingly
    """

    def __init__(
        self,
        ollama_model: str,
        guided_mode: bool = True,
        enable_fallback: bool = True,
        enable_natural_language_detection: bool = False,
        debug: bool = False
    ):
        """
        Initialize Universal Tool Adapter

        Args:
            ollama_model: Name of the Ollama model being used
            guided_mode: Whether to add detailed guidance in system prompts
            enable_fallback: Whether to fall back to prompt-based if native fails
            enable_natural_language_detection: Enable proactive tool detection
            debug: Enable debug logging
        """
        self.ollama_model = ollama_model
        self.guided_mode = guided_mode
        self.enable_fallback = enable_fallback
        self.debug = debug

        # Initialize components
        self.capabilities = ModelCapabilities()
        self.translator = FormatTranslator()
        self.prompt_gen = PromptGenerator(guided_mode=guided_mode)
        self.parser = ResponseParser(enable_natural_language_detection=enable_natural_language_detection)

        # Get model capabilities
        self.tier, self.format, self.supports_native = self.capabilities.get_capabilities(ollama_model)

        logger.info(
            f"UniversalToolAdapter initialized for {ollama_model}: "
            f"Tier {self.tier.value}, Format: {self.format}, "
            f"Native: {self.supports_native}"
        )

        if debug:
            logger.debug(f"Guided mode: {guided_mode}, Fallback: {enable_fallback}")

    def prepare_request(
        self,
        anthropic_request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Prepare Anthropic request for Ollama

        Transforms tool definitions and system prompts based on model capabilities

        Args:
            anthropic_request: Original request from Claude Code (Anthropic format)

        Returns:
            Dictionary with adapted request components
        """
        tools = anthropic_request.get("tools", [])
        original_system = anthropic_request.get("system", "")
        messages = anthropic_request.get("messages", [])

        logger.debug(f"Preparing request with {len(tools)} tools, {len(messages)} messages")

        # Adapt based on tier
        if self.tier == ModelTier.TIER_1_NATIVE_OPENAI:
            adapted = self._prepare_tier_1(tools, original_system)
        elif self.tier == ModelTier.TIER_2_PARTIAL:
            adapted = self._prepare_tier_2(tools, original_system)
        else:  # TIER_3
            adapted = self._prepare_tier_3(tools, original_system)

        adapted["tier"] = self.tier
        adapted["original_tools"] = tools

        if self.debug:
            logger.debug(f"Prepared request: {len(adapted.get('system', ''))} char system prompt")

        return adapted

    def _prepare_tier_1(
        self,
        tools: List[Dict[str, Any]],
        original_system: str
    ) -> Dict[str, Any]:
        """Prepare request for Tier 1 models (OpenAI-compatible)"""
        logger.debug("Preparing for Tier 1 (OpenAI native)")

        # Convert tools to OpenAI format
        ollama_tools = None
        if tools:
            ollama_tools = self.translator.anthropic_to_openai_tools(tools)

        # Generate system prompt (minimal for Tier 1)
        system_prompt = self.prompt_gen.for_tier_1_openai(tools, original_system)

        return {
            "ollama_tools": ollama_tools,
            "system": system_prompt,
            "format": "openai"
        }

    def _prepare_tier_2(
        self,
        tools: List[Dict[str, Any]],
        original_system: str
    ) -> Dict[str, Any]:
        """Prepare request for Tier 2 models (partial support)"""
        logger.debug("Preparing for Tier 2 (partial native)")

        # Try native format first
        ollama_tools = None
        if tools and self.supports_native:
            if self.format == "openai":
                ollama_tools = self.translator.anthropic_to_openai_tools(tools)
            # Add other formats as needed (deepseek, qwen, etc.)

        # Generate guided system prompt
        system_prompt = self.prompt_gen.for_tier_2_partial(tools, original_system)

        return {
            "ollama_tools": ollama_tools,
            "system": system_prompt,
            "format": self.format
        }

    def _prepare_tier_3(
        self,
        tools: List[Dict[str, Any]],
        original_system: str
    ) -> Dict[str, Any]:
        """Prepare request for Tier 3 models (prompt-based only)"""
        logger.debug("Preparing for Tier 3 (prompt-based)")

        # No native tools - use prompt-based approach
        # Don't send tools parameter to Ollama
        ollama_tools = None

        # Generate comprehensive prompt-based instructions
        system_prompt = self.prompt_gen.for_tier_3_prompt_based(tools, original_system)

        return {
            "ollama_tools": ollama_tools,
            "system": system_prompt,
            "format": "prompt-based"
        }

    def parse_response(
        self,
        ollama_response: Dict[str, Any],
        original_request: Dict[str, Any]
    ) -> Tuple[Optional[List[Dict[str, Any]]], Dict[str, Any]]:
        """
        Parse Ollama response and extract tool usage

        Args:
            ollama_response: Response from Ollama API
            original_request: Original Anthropic request

        Returns:
            Tuple of (content_blocks, metadata)
            content_blocks: List of Anthropic-format content blocks
            metadata: Additional metadata about parsing
        """
        # Parse for tool usage
        tool_use, text_content = self.parser.parse_response(
            ollama_response,
            self.tier,
            original_request
        )

        content_blocks = []
        metadata = {
            "tier": self.tier.value,
            "format": self.format,
            "tool_detected": tool_use is not None,
            "parsing_method": None
        }

        # Build content blocks
        if tool_use:
            # Validate tool use
            is_valid, error = self.parser.validate_tool_use(tool_use)

            if is_valid:
                content_blocks.append(tool_use)
                metadata["parsing_method"] = "tool_use"
                logger.info(f"Tool detected: {tool_use.get('name')}")

                # Add cleaned text if present
                cleaned_text = self.parser.clean_tool_response_text(text_content)
                if cleaned_text:
                    content_blocks.append({
                        "type": "text",
                        "text": cleaned_text
                    })
            else:
                logger.warning(f"Invalid tool use detected: {error}")
                # Fall back to text-only response
                content_blocks.append({
                    "type": "text",
                    "text": text_content
                })
                metadata["parsing_error"] = error
                metadata["parsing_method"] = "text_fallback"
        else:
            # No tool detected, return text content
            content_blocks.append({
                "type": "text",
                "text": text_content
            })
            metadata["parsing_method"] = "text_only"

        if self.debug:
            logger.debug(f"Parsed response: {len(content_blocks)} blocks, method: {metadata['parsing_method']}")

        return content_blocks, metadata

    def handle_tool_result(
        self,
        tool_result_message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle tool result messages from Claude Code

        Tool results need to be passed back to the model in a format it understands

        Args:
            tool_result_message: Message with tool_result content blocks

        Returns:
            Adapted message for Ollama
        """
        content = tool_result_message.get("content", [])

        adapted_content = []

        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                # Extract result content
                result_content = block.get("content", "")
                tool_use_id = block.get("tool_use_id", "")

                # Format based on tier
                if self.tier == ModelTier.TIER_1_NATIVE_OPENAI:
                    # OpenAI format expects result in specific structure
                    adapted_content.append({
                        "type": "function",
                        "function": {
                            "name": "tool_result",
                            "content": str(result_content)
                        }
                    })
                else:
                    # For other tiers, format as text
                    result_text = f"[Tool Result]\n{result_content}"
                    adapted_content.append(result_text)

        logger.debug(f"Adapted tool result for tier {self.tier.value}")

        return {
            "role": "user",  # Tool results come back as user messages
            "content": adapted_content
        }

    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about current model and capabilities

        Returns:
            Dictionary with model information
        """
        return {
            "model": self.ollama_model,
            "tier": self.tier.value,
            "tier_name": self.tier.name,
            "format": self.format,
            "supports_native_tools": self.supports_native,
            "guided_mode": self.guided_mode,
            "fallback_enabled": self.enable_fallback,
            "description": self.capabilities.get_description(self.ollama_model)
        }

    def update_model(self, new_model: str):
        """
        Update the model being used

        Useful for runtime model switching

        Args:
            new_model: New Ollama model name
        """
        logger.info(f"Switching model from {self.ollama_model} to {new_model}")

        self.ollama_model = new_model
        self.tier, self.format, self.supports_native = self.capabilities.get_capabilities(new_model)

        logger.info(
            f"Model updated: Tier {self.tier.value}, "
            f"Format: {self.format}, Native: {self.supports_native}"
        )

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get adapter statistics

        Returns:
            Dictionary with usage statistics
        """
        return {
            "model": self.ollama_model,
            "tier": self.tier.value,
            "capabilities": self.capabilities.get_statistics(),
            "guided_mode": self.guided_mode,
            "fallback_enabled": self.enable_fallback,
        }

    def test_tool_support(self) -> Dict[str, Any]:
        """
        Test tool support for current model

        Returns:
            Test results dictionary
        """
        sample_tools = [{
            "name": "test_tool",
            "description": "A test tool",
            "input_schema": {
                "type": "object",
                "properties": {
                    "param": {"type": "string"}
                }
            }
        }]

        adapted = self.prepare_request({
            "tools": sample_tools,
            "system": "Test system prompt",
            "messages": []
        })

        return {
            "model": self.ollama_model,
            "tier": self.tier.value,
            "supports_native": self.supports_native,
            "format": self.format,
            "would_use_native_tools": adapted["ollama_tools"] is not None,
            "system_prompt_length": len(adapted["system"]),
            "recommendation": self._get_recommendation()
        }

    def _get_recommendation(self) -> str:
        """Get recommendation for current model setup"""
        if self.tier == ModelTier.TIER_1_NATIVE_OPENAI:
            return "Excellent tool support - native function calling available"
        elif self.tier == ModelTier.TIER_2_PARTIAL:
            return "Good tool support - partial native support with guidance"
        else:
            return "Limited tool support - using prompt-based approach. Consider upgrading to a better model for autonomous tool use."
