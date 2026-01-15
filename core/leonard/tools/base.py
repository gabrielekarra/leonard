"""
Base classes for Leonard tools.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


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
    """Result of a tool execution."""
    success: bool
    output: Any
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }


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
