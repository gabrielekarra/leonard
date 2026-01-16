"""
Tool executor for Leonard.
Handles tool execution with safety checks and confirmations.
"""

import json
import re
from typing import Optional, Callable, Awaitable

from leonard.tools.base import Tool, ToolRegistry, ToolResult, RiskLevel
from leonard.tools.filesystem import FILESYSTEM_TOOLS
from leonard.tools.shell import SHELL_TOOLS
from leonard.tools.organizer import ORGANIZER_TOOLS
from leonard.utils.logging import logger


class ToolExecutor:
    """
    Executes tools requested by the AI model.
    Handles safety checks and user confirmations.
    """

    def __init__(
        self,
        confirmation_callback: Optional[Callable[[str, dict], Awaitable[bool]]] = None,
    ):
        """
        Initialize the tool executor.

        Args:
            confirmation_callback: Async function called to confirm dangerous operations.
                                   Takes (tool_name, parameters) and returns bool.
                                   If None, dangerous operations are auto-approved.
        """
        self.registry = ToolRegistry()
        self.confirmation_callback = confirmation_callback
        self._pending_confirmations: dict[str, dict] = {}

        # Register all tools
        self._register_default_tools()

    def _register_default_tools(self):
        """Register default tools."""
        for tool in FILESYSTEM_TOOLS:
            self.registry.register(tool)

        for tool in SHELL_TOOLS:
            self.registry.register(tool)

        for tool in ORGANIZER_TOOLS:
            self.registry.register(tool)

        logger.info(f"Registered {len(self.registry.list_all())} tools")

    def get_tools_prompt(self) -> str:
        """Get the prompt describing available tools."""
        return self.registry.get_tools_prompt()

    def parse_tool_call(self, text: str) -> Optional[tuple[str, dict]]:
        """
        Parse a tool call from the model's response.

        Args:
            text: The model's response text

        Returns:
            Tuple of (tool_name, parameters) if found, None otherwise
        """
        # Try multiple patterns to catch different model output formats

        # Pattern 1: ```tool{...}``` (no space/newline)
        pattern1 = r"```tool\s*({.*?})```"
        match = re.search(pattern1, text, re.DOTALL)

        # Pattern 2: ```tool\n{...}\n``` (with newlines)
        if not match:
            pattern2 = r"```tool\s*\n\s*({.*?})\s*\n?```"
            match = re.search(pattern2, text, re.DOTALL)

        # Pattern 3: ```json with tool inside
        if not match:
            pattern3 = r"```(?:json)?\s*({[^`]*\"tool\"[^`]*})```"
            match = re.search(pattern3, text, re.DOTALL)

        if match:
            try:
                data = json.loads(match.group(1))
                tool_name = data.get("tool")
                parameters = data.get("parameters", {})

                if tool_name:
                    logger.info(f"Parsed tool call: {tool_name} with params: {parameters}")
                    return (tool_name, parameters)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse tool call JSON: {match.group(1)}")

        # Pattern 4: Standalone JSON {"tool": "name", "parameters": {...}}
        alt_pattern = r'{\s*"tool"\s*:\s*"([^"]+)"\s*,\s*"parameters"\s*:\s*({[^}]*})\s*}'
        alt_match = re.search(alt_pattern, text, re.DOTALL)
        if alt_match:
            try:
                tool_name = alt_match.group(1)
                parameters = json.loads(alt_match.group(2))
                logger.info(f"Parsed tool call (alt format): {tool_name} with params: {parameters}")
                return (tool_name, parameters)
            except json.JSONDecodeError:
                pass

        logger.debug(f"No tool call found in response")
        return None

    async def execute(self, tool_name: str, parameters: dict) -> ToolResult:
        """
        Execute a tool with the given parameters.

        Args:
            tool_name: Name of the tool to execute
            parameters: Parameters for the tool

        Returns:
            ToolResult with success/failure and output
        """
        tool = self.registry.get(tool_name)

        if not tool:
            return ToolResult(
                success=False,
                output=None,
                error=f"Unknown tool: {tool_name}",
            )

        # Check if confirmation is needed
        if tool.requires_confirmation or tool.risk_level == RiskLevel.HIGH:
            if self.confirmation_callback:
                logger.info(f"Requesting confirmation for {tool_name}")
                approved = await self.confirmation_callback(tool_name, parameters)

                if not approved:
                    return ToolResult(
                        success=False,
                        output=None,
                        error="Operation cancelled by user",
                    )

        # Execute the tool
        try:
            logger.info(f"Executing tool: {tool_name} with params: {parameters}")
            result = await tool.execute(**parameters)
            logger.info(f"Tool {tool_name} completed: success={result.success}")
            return result

        except TypeError as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Invalid parameters for {tool_name}: {e}",
            )
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return ToolResult(
                success=False,
                output=None,
                error=f"Tool execution failed: {e}",
            )

    async def process_response(
        self, response: str
    ) -> tuple[str, Optional[ToolResult]]:
        """
        Process a model response, executing any tool calls.

        Args:
            response: The model's response text

        Returns:
            Tuple of (cleaned_response, tool_result)
            - cleaned_response: Response with tool block removed
            - tool_result: Result of tool execution, or None if no tool called
        """
        tool_call = self.parse_tool_call(response)

        if not tool_call:
            return (response, None)

        tool_name, parameters = tool_call
        result = await self.execute(tool_name, parameters)

        # Remove the tool block from response (handles multiple formats)
        cleaned = response

        # 1. Remove ```tool{...}``` blocks (with or without spaces/newlines)
        cleaned = re.sub(r"```tool\s*\{.*?\}```", "", cleaned, flags=re.DOTALL)

        # 2. Remove ```json{...}``` blocks
        cleaned = re.sub(r"```json\s*\{.*?\}```", "", cleaned, flags=re.DOTALL)

        # 3. Remove generic code blocks that contain "tool" JSON
        cleaned = re.sub(r"```[^`]*\"tool\"[^`]*```", "", cleaned, flags=re.DOTALL)

        # 4. Remove standalone tool JSON: {"tool": "...", "parameters": {...}}
        cleaned = re.sub(r'\{\s*["\']tool["\']\s*:\s*["\'][^"\']+["\']\s*,\s*["\']parameters["\']\s*:\s*\{[^}]*\}\s*\}', "", cleaned, flags=re.DOTALL)

        # 5. Remove Results: sections with code blocks
        cleaned = re.sub(r"Results?:\s*```[^`]*```", "", cleaned, flags=re.DOTALL)

        # 6. Remove Result: sections without code blocks (just JSON arrays/objects)
        cleaned = re.sub(r"Results?:\s*\[[^\]]*\]", "", cleaned, flags=re.DOTALL)

        # 7. Remove any remaining ```...``` blocks that look like JSON
        cleaned = re.sub(r"```\s*[\[\{].*?[\]\}]\s*```", "", cleaned, flags=re.DOTALL)

        # 8. Clean up leftover artifacts
        cleaned = re.sub(r"\n\s*\n\s*\n+", "\n\n", cleaned)
        cleaned = cleaned.strip()

        # 9. If response is now empty or just whitespace, use a generic success message
        if not cleaned or cleaned.isspace():
            cleaned = ""

        return (cleaned, result)

    def format_result_for_model(self, result: ToolResult) -> str:
        """Format a tool result as context for the model."""
        if result.success:
            output = result.output
            if isinstance(output, dict):
                output = json.dumps(output, indent=2)
            return f"Tool executed successfully. Result:\n{output}"
        else:
            return f"Tool execution failed: {result.error}"
