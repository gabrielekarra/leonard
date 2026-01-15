"""Tool registry for managing available MCP tools."""

from leonard.utils.logging import logger


class ToolRegistry:
    """Registry of available MCP tools."""

    def __init__(self) -> None:
        """Initialize the tool registry."""
        self._tools: dict[str, dict] = {}
        logger.info("ToolRegistry initialized")

    def register(self, tool_id: str, tool_info: dict) -> None:
        """Register a tool in the registry.

        Args:
            tool_id: Unique tool identifier
            tool_info: Tool metadata and configuration
        """
        self._tools[tool_id] = tool_info
        logger.info(f"Registered tool: {tool_id}")

    def unregister(self, tool_id: str) -> bool:
        """Remove a tool from the registry.

        Args:
            tool_id: The tool to remove

        Returns:
            True if tool was removed
        """
        if tool_id in self._tools:
            del self._tools[tool_id]
            logger.info(f"Unregistered tool: {tool_id}")
            return True
        return False

    def get(self, tool_id: str) -> dict | None:
        """Get tool information by ID."""
        return self._tools.get(tool_id)

    def list_tools(self) -> list[dict]:
        """Get all registered tools."""
        return list(self._tools.values())

    def is_registered(self, tool_id: str) -> bool:
        """Check if a tool is registered."""
        return tool_id in self._tools
