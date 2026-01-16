"""
Tests for tool detection patterns in the orchestrator.
Ensures that user requests are correctly mapped to tool calls.
"""

import os
import pytest
from leonard.engine.orchestrator import LeonardOrchestrator


class TestToolDetection:
    """Test the _detect_needed_tool method."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with tools enabled."""
        return LeonardOrchestrator(tools_enabled=True, rag_enabled=False)

    # ─────────────────────────────────────────────────────────
    # LIST DIRECTORY TESTS
    # ─────────────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "message,expected_path",
        [
            # English queries
            ("what files are in downloads", os.path.expanduser("~/Downloads")),
            ("list files in downloads folder", os.path.expanduser("~/Downloads")),
            ("show me what's in my downloads", os.path.expanduser("~/Downloads")),
            ("which files are in the downloads directory", os.path.expanduser("~/Downloads")),
            ("what's in downloads", os.path.expanduser("~/Downloads")),
            # Documents
            ("list files in documents", os.path.expanduser("~/Documents")),
            ("show documents folder contents", os.path.expanduser("~/Documents")),
            # Desktop
            ("what files are on desktop", os.path.expanduser("~/Desktop")),
            ("list desktop contents", os.path.expanduser("~/Desktop")),
            # Italian queries
            ("quali file ci sono nei scaricati", os.path.expanduser("~/Downloads")),
            ("elenca i file nella cartella documenti", os.path.expanduser("~/Documents")),
            ("cosa c'è sulla scrivania", os.path.expanduser("~/Desktop")),
            # Explicit paths
            ("list files in /tmp", "/tmp"),
            ("what files are in ~/Downloads", os.path.expanduser("~/Downloads")),
        ],
    )
    def test_list_directory_detection(self, orchestrator, message, expected_path):
        """Test detection of list_directory requests."""
        result = orchestrator._detect_needed_tool(message)

        assert result is not None, f"Expected tool detection for: {message}"
        tool_name, params = result
        assert tool_name == "list_directory", f"Expected list_directory, got {tool_name}"
        assert params.get("path") == expected_path, f"Expected path {expected_path}, got {params.get('path')}"

    # ─────────────────────────────────────────────────────────
    # READ FILE TESTS
    # ─────────────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "message,expected_path",
        [
            ("read file /tmp/test.txt", "/tmp/test.txt"),
            ("show me the contents of /Users/test/file.py", "/Users/test/file.py"),
            ("open /etc/hosts", "/etc/hosts"),
            ("leggi il file /tmp/nota.txt", "/tmp/nota.txt"),
            ("cosa c'è nel file /tmp/data.json", "/tmp/data.json"),
        ],
    )
    def test_read_file_detection(self, orchestrator, message, expected_path):
        """Test detection of read_file requests."""
        result = orchestrator._detect_needed_tool(message)

        assert result is not None, f"Expected tool detection for: {message}"
        tool_name, params = result
        assert tool_name == "read_file", f"Expected read_file, got {tool_name}"
        assert params.get("path") == expected_path, f"Expected path {expected_path}, got {params.get('path')}"

    # ─────────────────────────────────────────────────────────
    # CREATE FILE TESTS
    # ─────────────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "message,expected_path",
        [
            ("create file /tmp/test.txt", "/tmp/test.txt"),
            ("write a new file /tmp/hello.md", "/tmp/hello.md"),
            ("crea il file /tmp/nota.txt", "/tmp/nota.txt"),
        ],
    )
    def test_create_file_detection(self, orchestrator, message, expected_path):
        """Test detection of write_file requests."""
        result = orchestrator._detect_needed_tool(message)

        assert result is not None, f"Expected tool detection for: {message}"
        tool_name, params = result
        assert tool_name == "write_file", f"Expected write_file, got {tool_name}"
        assert params.get("path") == expected_path, f"Expected path {expected_path}, got {params.get('path')}"

    # ─────────────────────────────────────────────────────────
    # DELETE FILE TESTS
    # ─────────────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "message,expected_path",
        [
            ("delete file /tmp/test.txt", "/tmp/test.txt"),
            ("remove /tmp/old_file.txt", "/tmp/old_file.txt"),
            ("elimina il file /tmp/nota.txt", "/tmp/nota.txt"),
        ],
    )
    def test_delete_file_detection(self, orchestrator, message, expected_path):
        """Test detection of delete_file requests."""
        result = orchestrator._detect_needed_tool(message)

        assert result is not None, f"Expected tool detection for: {message}"
        tool_name, params = result
        assert tool_name == "delete_file", f"Expected delete_file, got {tool_name}"
        assert params.get("path") == expected_path, f"Expected path {expected_path}, got {params.get('path')}"

    # ─────────────────────────────────────────────────────────
    # MOVE/RENAME TESTS
    # ─────────────────────────────────────────────────────────

    def test_move_file_two_paths(self, orchestrator):
        """Test move with two explicit paths."""
        result = orchestrator._detect_needed_tool("move /tmp/a.txt to /tmp/b.txt")

        assert result is not None
        tool_name, params = result
        assert tool_name == "move_file"
        assert params.get("source") == "/tmp/a.txt"
        assert params.get("destination") == "/tmp/b.txt"

    def test_rename_file_to_new_name(self, orchestrator):
        """Test rename detection."""
        result = orchestrator._detect_needed_tool("rename /tmp/old.txt to new.txt")

        assert result is not None
        tool_name, params = result
        assert tool_name == "move_file"
        assert params.get("source") == "/tmp/old.txt"
        assert "new.txt" in params.get("destination", "")

    # ─────────────────────────────────────────────────────────
    # CREATE DIRECTORY TESTS
    # ─────────────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "message",
        [
            "create folder test in downloads",
            "create a new folder called myproject in documents",
            "crea una cartella backup sul desktop",
            "make a new directory /tmp/test_dir",
        ],
    )
    def test_create_directory_detection(self, orchestrator, message):
        """Test detection of create_directory requests."""
        result = orchestrator._detect_needed_tool(message)

        assert result is not None, f"Expected tool detection for: {message}"
        tool_name, params = result
        assert tool_name == "create_directory", f"Expected create_directory, got {tool_name}"
        assert "path" in params, f"Expected 'path' in params"

    # ─────────────────────────────────────────────────────────
    # ORGANIZE FILES TESTS
    # ─────────────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "message,expected_path",
        [
            ("organize files in downloads", os.path.expanduser("~/Downloads")),
            ("organize my downloads folder", os.path.expanduser("~/Downloads")),
            ("sort files in /tmp/messy", "/tmp/messy"),
            ("organizza i file nei documenti", os.path.expanduser("~/Documents")),
        ],
    )
    def test_organize_files_detection(self, orchestrator, message, expected_path):
        """Test detection of organize_files requests."""
        result = orchestrator._detect_needed_tool(message)

        assert result is not None, f"Expected tool detection for: {message}"
        tool_name, params = result
        assert tool_name == "organize_files", f"Expected organize_files, got {tool_name}"
        assert params.get("directory") == expected_path, f"Expected {expected_path}, got {params.get('directory')}"

    # ─────────────────────────────────────────────────────────
    # NEGATIVE TESTS
    # ─────────────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "message",
        [
            "hello",
            "what's the weather like",
            "tell me a joke",
            "how are you",
            "explain quantum physics",
        ],
    )
    def test_no_tool_detection(self, orchestrator, message):
        """Test that non-file queries don't trigger tools."""
        result = orchestrator._detect_needed_tool(message)
        assert result is None, f"Should not detect tool for: {message}"
