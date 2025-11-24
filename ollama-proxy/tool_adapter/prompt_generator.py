"""
System Prompt Generator
Generates model-specific system prompts to guide tool usage
"""

import json
import logging
from typing import List, Dict, Any, Optional
from .model_capabilities import ModelTier

logger = logging.getLogger(__name__)


class PromptGenerator:
    """Generate system prompts for different model tiers"""

    def __init__(self, guided_mode: bool = True):
        """
        Initialize prompt generator

        Args:
            guided_mode: Whether to add detailed guidance for tool usage
        """
        self.guided_mode = guided_mode
        logger.debug(f"PromptGenerator initialized (guided={guided_mode})")

    def generate_for_tier(
        self,
        tier: ModelTier,
        tools: List[Dict[str, Any]],
        original_system: Optional[str] = None
    ) -> str:
        """
        Generate appropriate system prompt based on model tier

        Args:
            tier: Model capability tier
            tools: List of Anthropic tool definitions
            original_system: Original system prompt from request

        Returns:
            Complete system prompt
        """
        if tier == ModelTier.TIER_1_NATIVE_OPENAI:
            prompt = self.for_tier_1_openai(tools, original_system)
        elif tier == ModelTier.TIER_2_PARTIAL:
            prompt = self.for_tier_2_partial(tools, original_system)
        else:  # TIER_3_PROMPT_BASED
            prompt = self.for_tier_3_prompt_based(tools, original_system)

        logger.debug(f"Generated system prompt for Tier {tier.value} ({len(prompt)} chars)")
        return prompt

    def for_tier_1_openai(
        self,
        tools: List[Dict[str, Any]],
        original_system: Optional[str] = None
    ) -> str:
        """
        Generate system prompt for Tier 1 models (OpenAI-compatible)

        These models have full native function calling, so we just need
        to mention tools are available
        """
        parts = []

        # Include original system prompt
        if original_system:
            parts.append(original_system)

        # Add minimal tool guidance if in guided mode
        if self.guided_mode and tools:
            tool_names = [t.get("name", "unknown") for t in tools]
            parts.append(
                f"\nYou have access to the following tools: {', '.join(tool_names)}. "
                "Use them when appropriate to complete tasks."
            )

        return "\n\n".join(parts) if parts else ""

    def for_tier_2_partial(
        self,
        tools: List[Dict[str, Any]],
        original_system: Optional[str] = None
    ) -> str:
        """
        Generate system prompt for Tier 2 models (partial support)

        These models have some function calling but benefit from guidance
        """
        parts = []

        # Include original system prompt
        if original_system:
            parts.append(original_system)

        # Add tool guidance
        if tools:
            if self.guided_mode:
                parts.append(self._generate_tier_2_guidance(tools))
            else:
                # Minimal guidance
                tool_list = self._format_tool_list_simple(tools)
                parts.append(f"\nAvailable tools:\n{tool_list}")

        return "\n\n".join(parts) if parts else ""

    def for_tier_3_prompt_based(
        self,
        tools: List[Dict[str, Any]],
        original_system: Optional[str] = None
    ) -> str:
        """
        Generate system prompt for Tier 3 models (prompt-based only)

        These models don't have native function calling, so we teach them
        via detailed prompts
        """
        parts = []

        # Include original system prompt
        if original_system:
            parts.append(original_system)

        # Add comprehensive tool instructions
        if tools:
            parts.append(self._generate_tier_3_instructions(tools))

        return "\n\n".join(parts) if parts else ""

    def _generate_tier_2_guidance(self, tools: List[Dict[str, Any]]) -> str:
        """Generate guidance for Tier 2 models"""
        tool_descriptions = []

        for tool in tools:
            name = tool.get("name", "unknown")
            desc = tool.get("description", "")
            schema = tool.get("input_schema", {})
            props = schema.get("properties", {})
            required = schema.get("required", [])

            # Format parameters
            params = []
            for param_name, param_info in props.items():
                param_type = param_info.get("type", "any")
                is_req = " (required)" if param_name in required else ""
                params.append(f"  - {param_name}: {param_type}{is_req}")

            tool_desc = f"• {name}: {desc}"
            if params:
                tool_desc += "\n" + "\n".join(params)

            tool_descriptions.append(tool_desc)

        guidance = f"""TOOL USAGE INSTRUCTIONS:

You have access to the following tools:

{chr(10).join(tool_descriptions)}

When you need to use a tool:
1. Identify which tool is appropriate for the task
2. Call the tool with the required parameters
3. Wait for the result before continuing your response

Example: If you need to read a file, call the read_file tool with the file_path parameter.
"""
        return guidance

    def _generate_tier_3_instructions(self, tools: List[Dict[str, Any]]) -> str:
        """Generate comprehensive instructions for Tier 3 models"""

        # Detailed tool descriptions
        tool_descriptions = []
        for tool in tools:
            name = tool.get("name", "unknown")
            desc = tool.get("description", "")
            schema = tool.get("input_schema", {})
            props = schema.get("properties", {})
            required = schema.get("required", [])

            # Build parameter documentation
            param_docs = []
            for param_name, param_info in props.items():
                param_type = param_info.get("type", "string")
                param_desc = param_info.get("description", "")
                is_req = param_name in required

                param_doc = f"    • {param_name} ({param_type})"
                if is_req:
                    param_doc += " [REQUIRED]"
                if param_desc:
                    param_doc += f": {param_desc}"
                param_docs.append(param_doc)

            tool_doc = f"  {name}:\n"
            tool_doc += f"    Description: {desc}\n"
            if param_docs:
                tool_doc += f"    Parameters:\n" + "\n".join(param_docs)

            tool_descriptions.append(tool_doc)

        # Generate examples
        examples = self._generate_tool_examples(tools)

        instructions = f"""╔══════════════════════════════════════════════════════════════════╗
║                    TOOL USAGE INSTRUCTIONS                       ║
╚══════════════════════════════════════════════════════════════════╝

You are an AI assistant with access to file system and execution tools.
You MUST use these tools to complete tasks that require file operations,
command execution, or other system interactions.

AVAILABLE TOOLS:

{chr(10).join(tool_descriptions)}

╔══════════════════════════════════════════════════════════════════╗
║                      HOW TO USE TOOLS                            ║
╚══════════════════════════════════════════════════════════════════╝

When you need to use a tool, respond EXACTLY in this format:

<tool>tool_name</tool>
<input>{{"parameter": "value", "another_parameter": "another_value"}}</input>

CRITICAL RULES:
1. Use the EXACT format shown above
2. Tool name must match one of the available tools
3. Input must be valid JSON with all required parameters
4. Only ONE tool per response
5. Do not add explanatory text with the tool call
6. After calling a tool, wait for the result before continuing

{examples}

IMPORTANT WORKFLOW:
1. User asks you to do something
2. If it requires a tool, respond with <tool>...</tool> and <input>...</input>
3. You will receive the tool result
4. Then provide your analysis/explanation based on the result

Remember: File operations, command execution, and system queries REQUIRE tools.
Do not try to guess file contents or command outputs - use the tools!
"""
        return instructions

    def _generate_tool_examples(self, tools: List[Dict[str, Any]]) -> str:
        """Generate usage examples for common tools"""
        examples = []

        # Map of tool names to example calls
        example_calls = {
            "read_file": {
                "scenario": "User asks: 'What's in server.py?'",
                "response": '<tool>read_file</tool>\n<input>{"file_path": "server.py"}</input>'
            },
            "write_file": {
                "scenario": "User asks: 'Create a file called test.txt with Hello World'",
                "response": '<tool>write_file</tool>\n<input>{"file_path": "test.txt", "content": "Hello World"}</input>'
            },
            "bash": {
                "scenario": "User asks: 'List all Python files'",
                "response": '<tool>bash</tool>\n<input>{"command": "ls *.py"}</input>'
            },
            "edit": {
                "scenario": "User asks: 'Change the port to 8080 in config.py'",
                "response": '<tool>edit</tool>\n<input>{"file_path": "config.py", "old_string": "PORT = 3000", "new_string": "PORT = 8080"}</input>'
            }
        }

        # Generate examples for available tools
        for tool in tools[:4]:  # Limit to first 4 tools to avoid overly long prompts
            name = tool.get("name", "")
            if name in example_calls:
                example = example_calls[name]
                examples.append(
                    f"Example: {example['scenario']}\n"
                    f"Your response:\n{example['response']}\n"
                )

        if examples:
            return "EXAMPLES:\n\n" + "\n".join(examples)
        return ""

    def _format_tool_list_simple(self, tools: List[Dict[str, Any]]) -> str:
        """Format a simple list of tools"""
        lines = []
        for tool in tools:
            name = tool.get("name", "unknown")
            desc = tool.get("description", "")
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines)

    def merge_with_original(
        self,
        original_system: Optional[str],
        tool_system: str
    ) -> str:
        """
        Merge original system prompt with tool instructions

        Args:
            original_system: Original system prompt from request
            tool_system: Generated tool usage instructions

        Returns:
            Merged system prompt
        """
        if not original_system:
            return tool_system

        if not tool_system:
            return original_system

        # Merge with separator
        return f"{original_system}\n\n{'=' * 70}\n\n{tool_system}"

    def should_add_tool_prompts(self, tools: List[Dict[str, Any]]) -> bool:
        """Check if tool prompts should be added"""
        # Only add if we have tools and guided mode is enabled
        return bool(tools) and self.guided_mode

    def get_tool_count_message(self, tools: List[Dict[str, Any]]) -> str:
        """Get a message about available tool count"""
        count = len(tools)
        if count == 0:
            return "No tools available"
        elif count == 1:
            return f"1 tool available: {tools[0].get('name', 'unknown')}"
        else:
            names = [t.get("name", "?") for t in tools[:3]]
            suffix = f" and {count - 3} more" if count > 3 else ""
            return f"{count} tools available: {', '.join(names)}{suffix}"
