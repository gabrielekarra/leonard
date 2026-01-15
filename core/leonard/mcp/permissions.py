"""Permission management for MCP tool execution."""

from enum import Enum

from leonard.utils.logging import logger


class PermissionLevel(Enum):
    """Permission levels for tool execution."""

    DENY = "deny"
    ASK = "ask"
    ALLOW = "allow"


class PermissionManager:
    """Manages permissions for tool execution."""

    def __init__(self) -> None:
        """Initialize the permission manager."""
        self._permissions: dict[str, PermissionLevel] = {}
        logger.info("PermissionManager initialized")

    def set_permission(self, tool_id: str, level: PermissionLevel) -> None:
        """Set permission level for a tool.

        Args:
            tool_id: The tool to configure
            level: The permission level to set
        """
        self._permissions[tool_id] = level
        logger.info(f"Set permission for {tool_id}: {level.value}")

    def get_permission(self, tool_id: str) -> PermissionLevel:
        """Get permission level for a tool.

        Args:
            tool_id: The tool to check

        Returns:
            The permission level (defaults to ASK)
        """
        return self._permissions.get(tool_id, PermissionLevel.ASK)

    def check_allowed(self, tool_id: str) -> bool:
        """Check if a tool is allowed to execute.

        Args:
            tool_id: The tool to check

        Returns:
            True if tool can execute without asking
        """
        return self.get_permission(tool_id) == PermissionLevel.ALLOW

    def check_denied(self, tool_id: str) -> bool:
        """Check if a tool is denied.

        Args:
            tool_id: The tool to check

        Returns:
            True if tool is blocked from execution
        """
        return self.get_permission(tool_id) == PermissionLevel.DENY
