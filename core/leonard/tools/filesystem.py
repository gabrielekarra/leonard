"""
Filesystem tools for Leonard.
"""

import os
import shutil
from pathlib import Path
from typing import Optional

from leonard.tools.base import (
    Tool,
    ToolCategory,
    ToolParameter,
    ToolResult,
    RiskLevel,
)
from leonard.utils.logging import logger


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
        try:
            file_path = Path(path).expanduser().resolve()

            if not file_path.exists():
                return ToolResult(success=False, output=None, error=f"File not found: {path}")

            if not file_path.is_file():
                return ToolResult(success=False, output=None, error=f"Not a file: {path}")

            # Check file size
            size = file_path.stat().st_size
            if size > 10 * 1024 * 1024:  # 10MB limit
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"File too large ({size / 1024 / 1024:.1f} MB). Maximum is 10 MB.",
                )

            # Read file
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        lines.append(f"\n... (truncated at {max_lines} lines)")
                        break
                    lines.append(line)

            content = "".join(lines)
            logger.info(f"Read file: {file_path} ({len(lines)} lines)")

            return ToolResult(success=True, output=content)

        except PermissionError:
            return ToolResult(success=False, output=None, error=f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


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
        try:
            dir_path = Path(path).expanduser().resolve()

            if not dir_path.exists():
                return ToolResult(success=False, output=None, error=f"Directory not found: {path}")

            if not dir_path.is_dir():
                return ToolResult(success=False, output=None, error=f"Not a directory: {path}")

            items = []
            for item in sorted(dir_path.iterdir()):
                name = item.name
                if not show_hidden and name.startswith("."):
                    continue

                item_type = "dir" if item.is_dir() else "file"
                size = ""
                if item.is_file():
                    size_bytes = item.stat().st_size
                    if size_bytes < 1024:
                        size = f"{size_bytes} B"
                    elif size_bytes < 1024 * 1024:
                        size = f"{size_bytes / 1024:.1f} KB"
                    else:
                        size = f"{size_bytes / 1024 / 1024:.1f} MB"

                items.append({
                    "name": name,
                    "type": item_type,
                    "size": size,
                })

            logger.info(f"Listed directory: {dir_path} ({len(items)} items)")

            # Format output as readable text
            output_lines = [f"Directory: {dir_path}", f"Total items: {len(items)}", ""]
            for item in items:
                icon = "📁" if item["type"] == "dir" else "📄"
                size_str = f" ({item['size']})" if item["size"] else ""
                output_lines.append(f"  {icon} {item['name']}{size_str}")

            return ToolResult(success=True, output="\n".join(output_lines))

        except PermissionError:
            return ToolResult(success=False, output=None, error=f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


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
        try:
            file_path = Path(path).expanduser().resolve()

            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            mode = "a" if append else "w"
            with open(file_path, mode, encoding="utf-8") as f:
                f.write(content)

            action = "appended to" if append else "wrote"
            logger.info(f"{action.capitalize()} file: {file_path}")

            return ToolResult(
                success=True,
                output=f"Successfully {action} {file_path}",
            )

        except PermissionError:
            return ToolResult(success=False, output=None, error=f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


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
        try:
            src_path = Path(source).expanduser().resolve()
            dst_path = Path(destination).expanduser().resolve()

            if not src_path.exists():
                return ToolResult(success=False, output=None, error=f"Source not found: {source}")

            # Create parent directories if needed
            dst_path.parent.mkdir(parents=True, exist_ok=True)

            shutil.move(str(src_path), str(dst_path))
            logger.info(f"Moved: {src_path} -> {dst_path}")

            return ToolResult(
                success=True,
                output=f"Successfully moved {src_path} to {dst_path}",
            )

        except PermissionError:
            return ToolResult(success=False, output=None, error="Permission denied")
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


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
        try:
            src_path = Path(source).expanduser().resolve()
            dst_path = Path(destination).expanduser().resolve()

            if not src_path.exists():
                return ToolResult(success=False, output=None, error=f"Source not found: {source}")

            # Create parent directories if needed
            dst_path.parent.mkdir(parents=True, exist_ok=True)

            if src_path.is_dir():
                shutil.copytree(str(src_path), str(dst_path))
            else:
                shutil.copy2(str(src_path), str(dst_path))

            logger.info(f"Copied: {src_path} -> {dst_path}")

            return ToolResult(
                success=True,
                output=f"Successfully copied {src_path} to {dst_path}",
            )

        except PermissionError:
            return ToolResult(success=False, output=None, error="Permission denied")
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


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
        try:
            target_path = Path(path).expanduser().resolve()

            if not target_path.exists():
                return ToolResult(success=False, output=None, error=f"Path not found: {path}")

            # Safety check - don't delete important directories
            dangerous_paths = [
                Path.home(),
                Path("/"),
                Path("/Users"),
                Path("/System"),
                Path("/Library"),
                Path("/Applications"),
            ]

            for dangerous in dangerous_paths:
                if target_path == dangerous or dangerous in target_path.parents:
                    if target_path == dangerous:
                        return ToolResult(
                            success=False,
                            output=None,
                            error=f"Cannot delete protected path: {path}",
                        )

            if target_path.is_dir():
                shutil.rmtree(str(target_path))
            else:
                target_path.unlink()

            logger.info(f"Deleted: {target_path}")

            return ToolResult(
                success=True,
                output=f"Successfully deleted {target_path}",
            )

        except PermissionError:
            return ToolResult(success=False, output=None, error="Permission denied")
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


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
        try:
            dir_path = Path(path).expanduser().resolve()

            if dir_path.exists():
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Path already exists: {path}",
                )

            dir_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created directory: {dir_path}")

            return ToolResult(
                success=True,
                output=f"Successfully created directory {dir_path}",
            )

        except PermissionError:
            return ToolResult(success=False, output=None, error="Permission denied")
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


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
        try:
            dir_path = Path(directory).expanduser().resolve()

            if not dir_path.exists():
                return ToolResult(
                    success=False, output=None, error=f"Directory not found: {directory}"
                )

            results = []
            for match in dir_path.glob(pattern):
                if len(results) >= max_results:
                    break
                results.append(str(match))

            logger.info(f"Search in {dir_path} for '{pattern}': {len(results)} results")

            return ToolResult(
                success=True,
                output={
                    "matches": results,
                    "count": len(results),
                    "truncated": len(results) >= max_results,
                },
            )

        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


# Export all filesystem tools
FILESYSTEM_TOOLS = [
    ReadFileTool(),
    ListDirectoryTool(),
    WriteFileTool(),
    MoveFileTool(),
    CopyFileTool(),
    DeleteFileTool(),
    CreateDirectoryTool(),
    SearchFilesTool(),
]
