"""
Tests for filesystem tools.
Tests each tool directly to ensure they work correctly.
"""

import os
import tempfile
import shutil
import pytest
from pathlib import Path

from leonard.tools.filesystem import (
    ReadFileTool,
    ListDirectoryTool,
    WriteFileTool,
    MoveFileTool,
    CopyFileTool,
    DeleteFileTool,
    CreateDirectoryTool,
    SearchFilesTool,
)


class TestListDirectoryTool:
    """Test the list_directory tool."""

    @pytest.fixture
    def tool(self):
        return ListDirectoryTool()

    @pytest.fixture
    def test_dir(self):
        """Create a temporary directory with test files."""
        temp_dir = tempfile.mkdtemp()
        # Create test files
        Path(temp_dir, "file1.txt").write_text("content1")
        Path(temp_dir, "file2.pdf").write_text("content2")
        Path(temp_dir, "image.png").write_bytes(b"\x89PNG")
        Path(temp_dir, "subdir").mkdir()
        Path(temp_dir, ".hidden").write_text("hidden")
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.mark.asyncio
    async def test_list_directory_success(self, tool, test_dir):
        """Test listing a directory."""
        result = await tool.execute(path=test_dir)

        assert result.success is True
        assert result.error is None
        assert "file1.txt" in result.output
        assert "file2.pdf" in result.output
        assert "image.png" in result.output
        assert "subdir" in result.output

    @pytest.mark.asyncio
    async def test_list_directory_hides_hidden_by_default(self, tool, test_dir):
        """Test that hidden files are hidden by default."""
        result = await tool.execute(path=test_dir)

        assert result.success is True
        assert ".hidden" not in result.output

    @pytest.mark.asyncio
    async def test_list_directory_shows_hidden(self, tool, test_dir):
        """Test showing hidden files."""
        result = await tool.execute(path=test_dir, show_hidden=True)

        assert result.success is True
        assert ".hidden" in result.output

    @pytest.mark.asyncio
    async def test_list_directory_not_found(self, tool):
        """Test listing non-existent directory."""
        result = await tool.execute(path="/nonexistent/path")

        assert result.success is False
        assert result.error is not None
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_list_downloads_folder(self, tool):
        """Test listing the actual Downloads folder."""
        downloads = os.path.expanduser("~/Downloads")
        result = await tool.execute(path=downloads)

        assert result.success is True
        # Should contain actual files, not hallucinated ones
        assert "Directory:" in result.output
        # Verify it contains files from actual Downloads
        actual_files = list(Path(downloads).iterdir())
        for f in actual_files[:3]:  # Check first 3 files
            if not f.name.startswith("."):
                assert f.name in result.output, f"Expected {f.name} in output"


class TestReadFileTool:
    """Test the read_file tool."""

    @pytest.fixture
    def tool(self):
        return ReadFileTool()

    @pytest.mark.asyncio
    async def test_read_file_success(self, tool):
        """Test reading a file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Hello, World!")
            f.flush()
            path = f.name

        try:
            result = await tool.execute(path=path)
            assert result.success is True
            assert "Hello, World!" in result.output
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_read_file_not_found(self, tool):
        """Test reading non-existent file."""
        result = await tool.execute(path="/nonexistent/file.txt")

        assert result.success is False
        assert "not found" in result.error.lower()


class TestWriteFileTool:
    """Test the write_file tool."""

    @pytest.fixture
    def tool(self):
        return WriteFileTool()

    @pytest.mark.asyncio
    async def test_write_file_success(self, tool):
        """Test writing a file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "test.txt")

            result = await tool.execute(path=path, content="Test content")

            assert result.success is True
            assert Path(path).exists()
            assert Path(path).read_text() == "Test content"

    @pytest.mark.asyncio
    async def test_write_file_append(self, tool):
        """Test appending to a file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "test.txt")
            Path(path).write_text("Line 1\n")

            result = await tool.execute(path=path, content="Line 2", append=True)

            assert result.success is True
            assert Path(path).read_text() == "Line 1\nLine 2"


class TestMoveFileTool:
    """Test the move_file tool."""

    @pytest.fixture
    def tool(self):
        return MoveFileTool()

    @pytest.mark.asyncio
    async def test_move_file_success(self, tool):
        """Test moving a file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            src = os.path.join(temp_dir, "source.txt")
            dst = os.path.join(temp_dir, "dest.txt")
            Path(src).write_text("content")

            result = await tool.execute(source=src, destination=dst)

            assert result.success is True
            assert not Path(src).exists()
            assert Path(dst).exists()
            assert Path(dst).read_text() == "content"

    @pytest.mark.asyncio
    async def test_rename_file(self, tool):
        """Test renaming a file (move to same directory)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            old_name = os.path.join(temp_dir, "old.txt")
            new_name = os.path.join(temp_dir, "new.txt")
            Path(old_name).write_text("content")

            result = await tool.execute(source=old_name, destination=new_name)

            assert result.success is True
            assert not Path(old_name).exists()
            assert Path(new_name).exists()


class TestDeleteFileTool:
    """Test the delete_file tool."""

    @pytest.fixture
    def tool(self):
        return DeleteFileTool()

    @pytest.mark.asyncio
    async def test_delete_file_success(self, tool):
        """Test deleting a file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "to_delete.txt")
            Path(path).write_text("content")

            result = await tool.execute(path=path)

            assert result.success is True
            assert not Path(path).exists()

    @pytest.mark.asyncio
    async def test_delete_directory(self, tool):
        """Test deleting a directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = os.path.join(temp_dir, "subdir")
            os.makedirs(dir_path)
            Path(dir_path, "file.txt").write_text("content")

            result = await tool.execute(path=dir_path)

            assert result.success is True
            assert not Path(dir_path).exists()

    @pytest.mark.asyncio
    async def test_delete_protected_path(self, tool):
        """Test that protected paths cannot be deleted."""
        result = await tool.execute(path=os.path.expanduser("~"))

        assert result.success is False
        assert "protected" in result.error.lower() or "cannot" in result.error.lower()


class TestCreateDirectoryTool:
    """Test the create_directory tool."""

    @pytest.fixture
    def tool(self):
        return CreateDirectoryTool()

    @pytest.mark.asyncio
    async def test_create_directory_success(self, tool):
        """Test creating a directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "new_folder")

            result = await tool.execute(path=path)

            assert result.success is True
            assert Path(path).exists()
            assert Path(path).is_dir()

    @pytest.mark.asyncio
    async def test_create_directory_exists(self, tool):
        """Test creating existing directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "existing")
            os.makedirs(path)

            result = await tool.execute(path=path)

            assert result.success is False
            assert "exists" in result.error.lower()


class TestSearchFilesTool:
    """Test the search_files tool."""

    @pytest.fixture
    def tool(self):
        return SearchFilesTool()

    @pytest.mark.asyncio
    async def test_search_files_success(self, tool):
        """Test searching for files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files
            Path(temp_dir, "file1.txt").write_text("content")
            Path(temp_dir, "file2.txt").write_text("content")
            Path(temp_dir, "file3.pdf").write_text("content")

            result = await tool.execute(directory=temp_dir, pattern="*.txt")

            assert result.success is True
            assert result.output["count"] == 2
            assert "file1.txt" in str(result.output["matches"])
            assert "file2.txt" in str(result.output["matches"])
            assert "file3.pdf" not in str(result.output["matches"])


class TestCopyFileTool:
    """Test the copy_file tool."""

    @pytest.fixture
    def tool(self):
        return CopyFileTool()

    @pytest.mark.asyncio
    async def test_copy_file_success(self, tool):
        """Test copying a file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            src = os.path.join(temp_dir, "source.txt")
            dst = os.path.join(temp_dir, "copy.txt")
            Path(src).write_text("content")

            result = await tool.execute(source=src, destination=dst)

            assert result.success is True
            assert Path(src).exists()  # Original still exists
            assert Path(dst).exists()  # Copy created
            assert Path(dst).read_text() == "content"
