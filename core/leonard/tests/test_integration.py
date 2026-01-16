"""
Integration tests for the orchestrator and tool execution.
Tests the full flow from user message to response.
"""

import os
import tempfile
import shutil
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from leonard.engine.orchestrator import LeonardOrchestrator
from leonard.tools.executor import ToolExecutor


class TestToolExecutorIntegration:
    """Test the ToolExecutor directly."""

    @pytest.fixture
    def executor(self):
        return ToolExecutor()

    @pytest.mark.asyncio
    async def test_list_directory_execution(self, executor):
        """Test that list_directory executes correctly."""
        downloads = os.path.expanduser("~/Downloads")
        result = await executor.execute("list_directory", {"path": downloads})

        assert result.success is True
        assert result.output is not None
        # Verify output contains actual directory listing format
        assert "Directory:" in result.output

    @pytest.mark.asyncio
    async def test_list_temp_directory(self, executor):
        """Test listing a temp directory with known files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create known files
            Path(temp_dir, "test1.txt").write_text("content")
            Path(temp_dir, "test2.pdf").write_text("content")

            result = await executor.execute("list_directory", {"path": temp_dir})

            assert result.success is True
            assert "test1.txt" in result.output
            assert "test2.pdf" in result.output
            # Should NOT contain hallucinated files
            assert "file1.txt" not in result.output
            assert "video.mp4" not in result.output


class TestOrchestratorToolDetection:
    """Test orchestrator's tool detection and execution flow."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator without initializing (no model needed for detection tests)."""
        return LeonardOrchestrator(tools_enabled=True, rag_enabled=False)

    def test_downloads_folder_detection(self, orchestrator):
        """Test that 'downloads' folder is correctly resolved."""
        result = orchestrator._detect_needed_tool("what files are in downloads")

        assert result is not None
        tool_name, params = result
        assert tool_name == "list_directory"
        assert params["path"] == os.path.expanduser("~/Downloads")

    def test_downloads_folder_italian(self, orchestrator):
        """Test Italian folder name detection."""
        result = orchestrator._detect_needed_tool("quali file ci sono nei scaricati")

        assert result is not None
        tool_name, params = result
        assert tool_name == "list_directory"
        assert params["path"] == os.path.expanduser("~/Downloads")


class TestOrchestratorMockedModel:
    """Test orchestrator with mocked model responses."""

    @pytest.fixture
    def orchestrator(self):
        return LeonardOrchestrator(tools_enabled=True, rag_enabled=False)

    @pytest.mark.asyncio
    async def test_auto_tool_triggers_before_model(self, orchestrator):
        """
        Test that auto-detected tools are triggered BEFORE the model generates.
        This is key - the tool should run first, then model uses results.
        """
        # Create temp dir with known files
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "actual_file.txt").write_text("content")

            # Patch the folder map to use our temp dir
            original_map = orchestrator.FOLDER_MAP.copy()
            orchestrator.FOLDER_MAP = {"testfolder": ""}
            orchestrator.USER_HOME = temp_dir

            # Mock process manager to avoid needing actual model
            mock_response = "Based on the files I found, here is the listing."
            orchestrator.process_manager.chat = AsyncMock(return_value=mock_response)

            # Mock router
            mock_decision = MagicMock()
            mock_decision.model_id = "test-model"
            orchestrator.router.route = AsyncMock(return_value=mock_decision)
            orchestrator.router.ensure_router_ready = AsyncMock()

            # Mock model ready state
            orchestrator.process_manager.is_running = MagicMock(return_value=True)
            orchestrator._initialized = True

            # Run chat
            result = await orchestrator.chat(f"what files are in {temp_dir}")

            # Verify tool was executed
            assert orchestrator._last_tool_result is not None
            assert orchestrator._last_tool_result.get("success") is True

            # Restore
            orchestrator.FOLDER_MAP = original_map


class TestActualDownloadsContent:
    """Test that actual Downloads folder content is returned."""

    @pytest.fixture
    def executor(self):
        return ToolExecutor()

    @pytest.mark.asyncio
    async def test_downloads_returns_real_files(self, executor):
        """Verify that listing Downloads returns real files, not hallucinated ones."""
        downloads = os.path.expanduser("~/Downloads")
        result = await executor.execute("list_directory", {"path": downloads})

        # Get actual files in Downloads
        actual_files = []
        for item in Path(downloads).iterdir():
            if not item.name.startswith("."):
                actual_files.append(item.name)

        # Verify tool returns actual files
        for filename in actual_files[:5]:  # Check first 5
            assert filename in result.output, f"Expected '{filename}' in output"

        # Verify no common hallucinated filenames
        hallucinated = ["file1.txt", "file2.pdf", "image.jpg", "video.mp4", "script.py", "document.docx"]
        for fake in hallucinated:
            if fake not in actual_files:  # Only check if it's not actually there
                assert fake not in result.output, f"Hallucinated file '{fake}' found in output"


class TestFileOperationsEndToEnd:
    """End-to-end tests for file operations."""

    @pytest.fixture
    def executor(self):
        return ToolExecutor()

    @pytest.mark.asyncio
    async def test_create_read_delete_flow(self, executor):
        """Test complete file lifecycle: create → read → delete."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "lifecycle_test.txt")
            content = "Test content for lifecycle"

            # Create
            result = await executor.execute("write_file", {"path": test_file, "content": content})
            assert result.success is True

            # Read
            result = await executor.execute("read_file", {"path": test_file})
            assert result.success is True
            assert content in result.output

            # Delete
            result = await executor.execute("delete_file", {"path": test_file})
            assert result.success is True
            assert not Path(test_file).exists()

    @pytest.mark.asyncio
    async def test_create_folder_and_organize(self, executor):
        """Test creating folder and moving files into it."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create some files
            file1 = os.path.join(temp_dir, "doc1.txt")
            file2 = os.path.join(temp_dir, "doc2.txt")
            Path(file1).write_text("content1")
            Path(file2).write_text("content2")

            # Create subfolder
            subfolder = os.path.join(temp_dir, "documents")
            result = await executor.execute("create_directory", {"path": subfolder})
            assert result.success is True

            # Move files
            result = await executor.execute("move_file", {
                "source": file1,
                "destination": os.path.join(subfolder, "doc1.txt")
            })
            assert result.success is True

            # List subfolder
            result = await executor.execute("list_directory", {"path": subfolder})
            assert result.success is True
            assert "doc1.txt" in result.output


class TestToolResultFormatting:
    """Test that tool results are properly formatted for the model."""

    @pytest.fixture
    def executor(self):
        return ToolExecutor()

    @pytest.mark.asyncio
    async def test_list_result_is_readable(self, executor):
        """Test that list_directory returns human-readable output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "file.txt").write_text("content")

            result = await executor.execute("list_directory", {"path": temp_dir})

            # Check formatting
            assert "Directory:" in result.output
            assert "Total items:" in result.output
            # Should have file icons
            assert "📄" in result.output or "file.txt" in result.output

    def test_format_result_for_model(self, executor):
        """Test format_result_for_model produces clean output."""
        from leonard.tools.base import ToolResult

        result = ToolResult(success=True, output="File list:\n- file1.txt\n- file2.txt")
        formatted = executor.format_result_for_model(result)

        assert "Tool executed successfully" in formatted
        assert "file1.txt" in formatted
