"""Filesystem tools for Leonard with verified operations."""

from leonard.tools.base import Tool, ToolCategory, ToolParameter, ToolResult, RiskLevel
from leonard.tools.file_ops import FileOperations


class ReadFileTool(Tool):
    """Read contents of a file."""

    def __init__(self):
        super().__init__(
            name="read_file",
            description="Read the contents of a file. Use this to view text files, code, documents, etc.",
            category=ToolCategory.FILESYSTEM,
            risk_level=RiskLevel.LOW,
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Path to the file to read",
                    required=True,
                ),
                ToolParameter(
                    name="max_lines",
                    type="integer",
                    description="Maximum number of lines to read (default: 100)",
                    required=False,
                    default=100,
                ),
            ],
        )

    async def execute(self, path: str, max_lines: int = 100) -> ToolResult:
        return FileOperations.read_file(path=path, max_lines=max_lines)


class ListDirectoryTool(Tool):
    """List contents of a directory."""

    def __init__(self):
        super().__init__(
            name="list_directory",
            description="List files and folders in a directory",
            category=ToolCategory.FILESYSTEM,
            risk_level=RiskLevel.LOW,
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Path to the directory to list",
                    required=True,
                ),
                ToolParameter(
                    name="show_hidden",
                    type="boolean",
                    description="Include hidden files (starting with .)",
                    required=False,
                    default=False,
                ),
            ],
        )

    async def execute(self, path: str, show_hidden: bool = False) -> ToolResult:
        return FileOperations.list_directory(path=path, show_hidden=show_hidden)


class WriteFileTool(Tool):
    """Write content to a file."""

    def __init__(self):
        super().__init__(
            name="write_file",
            description="Write content to a file. Creates the file if it doesn't exist.",
            category=ToolCategory.FILESYSTEM,
            risk_level=RiskLevel.MEDIUM,
            requires_confirmation=True,
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Path to the file to write",
                    required=True,
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description="Content to write to the file",
                    required=True,
                ),
                ToolParameter(
                    name="append",
                    type="boolean",
                    description="Append to file instead of overwriting",
                    required=False,
                    default=False,
                ),
            ],
        )

    async def execute(self, path: str, content: str, append: bool = False) -> ToolResult:
        return FileOperations.write_file(path=path, content=content, append=append)


class MoveFileTool(Tool):
    """Move or rename a file/directory."""

    def __init__(self):
        super().__init__(
            name="move_file",
            description="Move or rename a file or directory",
            category=ToolCategory.FILESYSTEM,
            risk_level=RiskLevel.MEDIUM,
            requires_confirmation=True,
            parameters=[
                ToolParameter(
                    name="source",
                    type="string",
                    description="Path to the file/directory to move",
                    required=True,
                ),
                ToolParameter(
                    name="destination",
                    type="string",
                    description="Destination path",
                    required=True,
                ),
            ],
        )

    async def execute(self, source: str, destination: str) -> ToolResult:
        return FileOperations.move_file(source=source, destination=destination)


class CopyFileTool(Tool):
    """Copy a file or directory."""

    def __init__(self):
        super().__init__(
            name="copy_file",
            description="Copy a file or directory",
            category=ToolCategory.FILESYSTEM,
            risk_level=RiskLevel.MEDIUM,
            requires_confirmation=True,
            parameters=[
                ToolParameter(
                    name="source",
                    type="string",
                    description="Path to the file/directory to copy",
                    required=True,
                ),
                ToolParameter(
                    name="destination",
                    type="string",
                    description="Destination path",
                    required=True,
                ),
            ],
        )

    async def execute(self, source: str, destination: str) -> ToolResult:
        return FileOperations.copy_file(source=source, destination=destination)


class DeleteFileTool(Tool):
    """Delete a file or directory."""

    def __init__(self):
        super().__init__(
            name="delete_file",
            description="Delete a file or directory. Use with caution!",
            category=ToolCategory.FILESYSTEM,
            risk_level=RiskLevel.HIGH,
            requires_confirmation=True,
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Path to the file/directory to delete",
                    required=True,
                ),
            ],
        )

    async def execute(self, path: str) -> ToolResult:
        return FileOperations.delete_file(path=path)


class DeleteByPatternTool(Tool):
    """Delete files matching a pattern in a directory."""

    def __init__(self):
        super().__init__(
            name="delete_by_pattern",
            description="Delete all files matching a pattern in a directory",
            category=ToolCategory.FILESYSTEM,
            risk_level=RiskLevel.HIGH,
            requires_confirmation=True,
            parameters=[
                ToolParameter(
                    name="directory",
                    type="string",
                    description="Directory to delete files from",
                    required=True,
                ),
                ToolParameter(
                    name="pattern",
                    type="string",
                    description="Glob pattern(s) to match, comma-separated (e.g., 'Screenshot*.png' or '*.jpg,*.png')",
                    required=True,
                ),
            ],
        )

    async def execute(self, directory: str, pattern: str) -> ToolResult:
        return FileOperations.delete_by_pattern(directory=directory, pattern=pattern)


class CreateDirectoryTool(Tool):
    """Create a directory."""

    def __init__(self):
        super().__init__(
            name="create_directory",
            description="Create a new directory",
            category=ToolCategory.FILESYSTEM,
            risk_level=RiskLevel.LOW,
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Path of the directory to create",
                    required=True,
                ),
            ],
        )

    async def execute(self, path: str) -> ToolResult:
        return FileOperations.create_directory(path=path)


class SearchFilesTool(Tool):
    """Search for files by name pattern."""

    def __init__(self):
        super().__init__(
            name="search_files",
            description="Search for files matching a pattern in a directory",
            category=ToolCategory.FILESYSTEM,
            risk_level=RiskLevel.LOW,
            parameters=[
                ToolParameter(
                    name="directory",
                    type="string",
                    description="Directory to search in",
                    required=True,
                ),
                ToolParameter(
                    name="pattern",
                    type="string",
                    description="Glob pattern to match (e.g., '*.txt', '**/*.py')",
                    required=True,
                ),
                ToolParameter(
                    name="max_results",
                    type="integer",
                    description="Maximum number of results (default: 50)",
                    required=False,
                    default=50,
                ),
            ],
        )

    async def execute(
        self, directory: str, pattern: str, max_results: int = 50
    ) -> ToolResult:
        return FileOperations.search_files(directory=directory, pattern=pattern, max_results=max_results)


# Export all filesystem tools
FILESYSTEM_TOOLS = [
    ReadFileTool(),
    ListDirectoryTool(),
    WriteFileTool(),
    MoveFileTool(),
    CopyFileTool(),
    DeleteFileTool(),
    DeleteByPatternTool(),
    CreateDirectoryTool(),
    SearchFilesTool(),
]
