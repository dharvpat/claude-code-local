"""
Format Translator
Converts between Anthropic, OpenAI, and prompt-based tool formats
"""

import json
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class FormatTranslator:
    """Translate tool definitions and responses between formats"""

    def __init__(self):
        logger.debug("FormatTranslator initialized")

    # ========== TOOL DEFINITION TRANSLATIONS ==========

    def anthropic_to_openai_tools(self, anthropic_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert Anthropic tool format to OpenAI format

        Anthropic:
        {
          "name": "read_file",
          "description": "Read a file",
          "input_schema": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"]
          }
        }

        OpenAI:
        {
          "type": "function",
          "function": {
            "name": "read_file",
            "description": "Read a file",
            "parameters": {
              "type": "object",
              "properties": {"file_path": {"type": "string"}},
              "required": ["file_path"]
            }
          }
        }
        """
        openai_tools = []

        for tool in anthropic_tools:
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {})
                }
            }
            openai_tools.append(openai_tool)

        logger.debug(f"Converted {len(anthropic_tools)} Anthropic tools to OpenAI format")
        return openai_tools

    def anthropic_to_prompt_description(self, anthropic_tools: List[Dict[str, Any]]) -> str:
        """
        Convert Anthropic tools to prompt-based text description

        Returns a formatted string describing available tools
        """
        if not anthropic_tools:
            return ""

        lines = ["AVAILABLE TOOLS:"]
        lines.append("")

        for tool in anthropic_tools:
            name = tool.get("name", "unknown")
            desc = tool.get("description", "")
            schema = tool.get("input_schema", {})
            props = schema.get("properties", {})
            required = schema.get("required", [])

            # Build parameter list
            params = []
            for param_name, param_info in props.items():
                param_type = param_info.get("type", "any")
                param_desc = param_info.get("description", "")
                is_required = param_name in required

                param_str = f"{param_name}: {param_type}"
                if is_required:
                    param_str += " (required)"
                if param_desc:
                    param_str += f" - {param_desc}"

                params.append(param_str)

            # Format tool entry
            tool_line = f"• {name}("
            if params:
                tool_line += ", ".join([p.split(":")[0] for p in props.keys()])
            tool_line += ")"

            lines.append(tool_line)
            if desc:
                lines.append(f"  Description: {desc}")
            if params:
                lines.append(f"  Parameters:")
                for param in params:
                    lines.append(f"    - {param}")
            lines.append("")

        return "\n".join(lines)

    # ========== TOOL USE TRANSLATIONS (Response → Anthropic) ==========

    def openai_to_anthropic_tool_use(self, openai_response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Convert OpenAI function_call to Anthropic tool_use

        OpenAI:
        {
          "function_call": {
            "name": "read_file",
            "arguments": "{\"file_path\": \"server.py\"}"
          }
        }

        Anthropic:
        {
          "type": "tool_use",
          "id": "toolu_123",
          "name": "read_file",
          "input": {"file_path": "server.py"}
        }
        """
        function_call = openai_response.get("function_call")
        if not function_call:
            # Try alternative format
            tool_calls = openai_response.get("tool_calls", [])
            if tool_calls:
                function_call = tool_calls[0].get("function")

        if not function_call:
            return None

        name = function_call.get("name", "")
        arguments_str = function_call.get("arguments", "{}")

        try:
            # Parse JSON arguments
            if isinstance(arguments_str, str):
                input_data = json.loads(arguments_str)
            else:
                input_data = arguments_str
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse arguments as JSON: {arguments_str}")
            input_data = {"raw": arguments_str}

        tool_use = {
            "type": "tool_use",
            "id": f"toolu_{hash(json.dumps(function_call)) % 100000:05d}",
            "name": name,
            "input": input_data
        }

        logger.debug(f"Converted OpenAI function_call to Anthropic tool_use: {name}")
        return tool_use

    def prompt_based_to_anthropic_tool_use(
        self,
        text: str,
        tool_tag: str = "tool",
        input_tag: str = "input"
    ) -> Optional[Dict[str, Any]]:
        """
        Extract tool use from prompt-based text response

        Expected format:
        <tool>read_file</tool>
        <input>{"file_path": "server.py"}</input>

        Returns Anthropic tool_use dict or None
        """
        import re

        # Try XML-style tags
        tool_pattern = f"<{tool_tag}>(.*?)</{tool_tag}>"
        input_pattern = f"<{input_tag}>(.*?)</{input_tag}>"

        tool_match = re.search(tool_pattern, text, re.DOTALL)
        input_match = re.search(input_pattern, text, re.DOTALL)

        if not tool_match:
            logger.debug("No tool tag found in response")
            return None

        tool_name = tool_match.group(1).strip()

        # Parse input
        input_data = {}
        if input_match:
            input_str = input_match.group(1).strip()
            try:
                input_data = json.loads(input_str)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse input JSON: {input_str}")
                # Try to extract as key=value pairs
                input_data = {"raw": input_str}

        tool_use = {
            "type": "tool_use",
            "id": f"toolu_{hash(tool_name + str(input_data)) % 100000:05d}",
            "name": tool_name,
            "input": input_data
        }

        logger.debug(f"Extracted prompt-based tool use: {tool_name}")
        return tool_use

    def detect_natural_language_tool_intent(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Detect tool usage intent from natural language

        Patterns like:
        - "I need to read the file server.py"
        - "Let me run the command ls -la"
        - "I'll write to config.json"

        This is for proactive mode only, returns best guess
        """
        import re

        patterns = {
            "read_file": [
                r"(?:need to|should|will|let me|i'll)\s+read\s+(?:the\s+file\s+)?(['\"]?[\w./\-]+\.\w+['\"]?)",
                r"(?:read|reading|check)\s+(?:the\s+)?file\s+(['\"]?[\w./\-]+\.\w+['\"]?)",
            ],
            "write_file": [
                r"(?:need to|should|will|let me|i'll)\s+write\s+(?:to\s+)?(?:the\s+file\s+)?(['\"]?[\w./\-]+\.\w+['\"]?)",
                r"(?:create|creating)\s+(?:a\s+)?file\s+(?:called\s+)?(['\"]?[\w./\-]+\.\w+['\"]?)",
            ],
            "bash": [
                r"(?:need to|should|will|let me|i'll)\s+(?:run|execute)\s+(?:the\s+command\s+)?['\"](.+?)['\"]",
                r"(?:run|running|execute|executing)\s+['\"](.+?)['\"]",
            ],
        }

        for tool_name, pattern_list in patterns.items():
            for pattern in pattern_list:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    param = match.group(1).strip().strip("'\"")

                    # Build input based on tool
                    if tool_name in ["read_file", "write_file"]:
                        input_data = {"file_path": param}
                    elif tool_name == "bash":
                        input_data = {"command": param}
                    else:
                        input_data = {"value": param}

                    logger.info(f"Detected natural language tool intent: {tool_name}")
                    return {
                        "type": "tool_use",
                        "id": f"toolu_{hash(tool_name + param) % 100000:05d}",
                        "name": tool_name,
                        "input": input_data,
                        "_detected": True  # Mark as auto-detected
                    }

        return None

    # ========== HELPER METHODS ==========

    def tool_use_to_text(self, tool_use: Dict[str, Any]) -> str:
        """
        Convert Anthropic tool_use to text description
        Used for models that don't understand tool formats
        """
        name = tool_use.get("name", "unknown")
        input_data = tool_use.get("input", {})

        return f"[Tool: {name}, Input: {json.dumps(input_data)}]"

    def is_tool_use_block(self, content_block: Any) -> bool:
        """Check if a content block is a tool_use"""
        if not isinstance(content_block, dict):
            return False
        return content_block.get("type") == "tool_use"

    def is_tool_result_block(self, content_block: Any) -> bool:
        """Check if a content block is a tool_result"""
        if not isinstance(content_block, dict):
            return False
        return content_block.get("type") == "tool_result"

    def extract_tool_definitions_info(self, tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract summary information about tool definitions

        Useful for logging and debugging
        """
        if not tools:
            return {"count": 0, "names": []}

        names = [t.get("name", "unknown") for t in tools]
        param_counts = {}

        for tool in tools:
            name = tool.get("name", "unknown")
            schema = tool.get("input_schema", {})
            props = schema.get("properties", {})
            param_counts[name] = len(props)

        return {
            "count": len(tools),
            "names": names,
            "parameter_counts": param_counts
        }
