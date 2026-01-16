"""
Base classes for Leonard tools.
Defines the shared ToolResult/verification contract used across the system.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Optional


class ToolCategory(str, Enum):
    """Categories of tools."""
    FILESYSTEM = "filesystem"
    SHELL = "shell"
    WEB = "web"
    SYSTEM = "system"


class RiskLevel(str, Enum):
    """Risk level of a tool operation."""
    LOW = "low"          # Read-only operations
    MEDIUM = "medium"    # Write operations in safe directories
    HIGH = "high"        # Destructive or system-wide operations


@dataclass
class ToolResult:
    """
    Result of a tool execution.

    status: "success" | "error"
    action: semantic action name (create|move|delete|list|index|read|other)
    changed: affected file paths (before/after where applicable)
    verification: post-op verification outcome
    message_internal: structured/debug detail
    message_user: optional short, user-facing text
    """

    status: Literal["success", "error"]
    action: Optional[str]
    output: Any
    error: Optional[str] = None
    # Mutation tracking - single source of truth for filesystem changes.
    before_paths: list[str] = field(default_factory=list)
    after_paths: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    # Verification results (required for mutations).
    verification: Optional["VerificationResult"] = None
    verification_passed: Optional[bool] = None
    verification_details: Optional[str] = None
    # User-visible summary supplied by tools/formatter pipeline only.
    display_summary_user: Optional[str] = None
    message_internal: Optional[str] = None
    message_user: Optional[str] = None

    @property
    def success(self) -> bool:
        """Compatibility alias for callers expecting a boolean."""
        return self.status == "success"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "success": self.success,
            "action": self.action,
            "output": self.output,
            "error": self.error,
            "before_paths": self.before_paths,
            "after_paths": self.after_paths,
            "changed": self.changed,
            "verification": self.verification.to_dict() if self.verification else None,
            "verification_passed": self.verification_passed,
            "verification_details": self.verification_details,
            "display_summary_user": self.display_summary_user,
            "message_internal": self.message_internal,
            "message_user": self.message_user,
        }


@dataclass
class VerificationResult:
    """Represents the verification status of a tool action."""

    passed: bool
    details: str

    def to_dict(self) -> dict:
        return {"passed": self.passed, "details": self.details}


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""
    name: str
    type: str  # "string", "integer", "boolean", "array"
    description: str
    required: bool = True
    default: Any = None


@dataclass
class Tool(ABC):
    """Base class for all tools."""
    name: str
    description: str
    category: ToolCategory
    risk_level: RiskLevel
    parameters: list[ToolParameter] = field(default_factory=list)
    requires_confirmation: bool = False
    enabled: bool = True

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters."""
        pass

    def to_schema(self) -> dict:
        """Convert tool to JSON schema for LLM."""
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = {
                "type": param.type,
                "description": param.description,
            }
            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        """Register a tool."""
        self._tools[tool.name] = tool

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """Enable or disable a tool by name."""
        tool = self._tools.get(name)
        if not tool:
            return False
        tool.enabled = enabled
        return True

    def is_enabled(self, name: str) -> bool:
        """Check whether a tool is enabled."""
        tool = self._tools.get(name)
        return bool(tool and tool.enabled)

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_all(self) -> list[Tool]:
        """List all registered tools."""
        return list(self._tools.values())

    def get_schemas(self) -> list[dict]:
        """Get JSON schemas for all tools (for LLM)."""
        return [tool.to_schema() for tool in self._tools.values()]

    def get_tools_prompt(self) -> str:
        """Generate a prompt describing available tools."""
        lines = ["# Available Tools\n"]
        lines.append("You MUST use these tools to interact with the file system. Do NOT guess or make up file contents.\n")

        for tool in self._tools.values():
            params_desc = ", ".join(
                f"{p.name}: {p.type}" + (" (required)" if p.required else " (optional)")
                for p in tool.parameters
            )
            lines.append(f"## {tool.name}")
            lines.append(f"{tool.description}")
            if params_desc:
                lines.append(f"Parameters: {params_desc}")
            lines.append("")

        lines.append("""
# How to Use Tools

You MUST use tools for ANY file system operation. Respond with a JSON block in this format:

```tool
{"tool": "tool_name", "parameters": {"param1": "value1"}}
```

EXAMPLES:

List files:
```tool
{"tool": "list_directory", "parameters": {"path": "/Users/example/Downloads"}}
```

Read a file:
```tool
{"tool": "read_file", "parameters": {"path": "/Users/example/file.txt"}}
```

RENAME a file (use move_file):
```tool
{"tool": "move_file", "parameters": {"source": "/Users/example/old_name.txt", "destination": "/Users/example/new_name.txt"}}
```

Create/write a file:
```tool
{"tool": "write_file", "parameters": {"path": "/Users/example/new_file.txt", "content": "Hello world"}}
```

Delete a file:
```tool
{"tool": "delete_file", "parameters": {"path": "/Users/example/unwanted.txt"}}
```

Run a command:
```tool
{"tool": "run_command", "parameters": {"command": "ls -la"}}
```

IMPORTANT:
- You CAN perform ANY file operation. Do NOT say you cannot do something.
- To RENAME: use move_file with same directory but different filename.
- To MODIFY: read_file first, then write_file with changes.
- After tool execution, report the results to the user.
""")

        return "\n".join(lines)
