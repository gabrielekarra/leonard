import os
import tempfile
from pathlib import Path

import pytest

from leonard.tools.file_ops import FileOperations
from leonard.tools.filesystem import DeleteFileTool, ListDirectoryTool, MoveFileTool, WriteFileTool
from leonard.utils.response_formatter import ResponseFormatter


def test_write_and_verify_file():
    with tempfile.TemporaryDirectory(dir="/tmp") as temp_dir:
        path = Path(temp_dir) / "note.txt"

        result = FileOperations.write_file(str(path), "hello world")

        assert result.status == "success"
        assert result.verification and result.verification.passed
        assert path.exists()
        assert path.read_text() == "hello world"


def test_move_verifies_source_removed():
    with tempfile.TemporaryDirectory(dir="/tmp") as temp_dir:
        src = Path(temp_dir) / "src.txt"
        dst = Path(temp_dir) / "dst.txt"
        src.write_text("move me")

        result = FileOperations.move_file(str(src), str(dst))

        assert result.status == "success"
        assert result.verification and result.verification.passed
        assert result.before_paths == [str(src)]
        assert result.after_paths == [str(dst)]
        assert result.verification_passed is True
        assert not src.exists()
        assert dst.exists()
        assert dst.read_text() == "move me"


def test_delete_reports_missing_cleanly():
    missing_path = "/tmp/does-not-exist.txt"
    result = FileOperations.delete_file(missing_path)

    assert result.status == "error"
    assert result.verification and not result.verification.passed
    assert "not found" in (result.message_user or "").lower()


def test_delete_tracks_before_after():
    with tempfile.TemporaryDirectory(dir="/tmp") as temp_dir:
        path = Path(temp_dir) / "remove.txt"
        path.write_text("remove me")

        result = FileOperations.delete_file(str(path))

        assert result.status == "success"
        assert result.before_paths == [str(path)]
        assert result.after_paths == []
        assert result.verification_passed is True
        assert not path.exists()


def test_list_directory_outputs_items():
    with tempfile.TemporaryDirectory(dir="/tmp") as temp_dir:
        Path(temp_dir, "a.txt").write_text("a")
        Path(temp_dir, "b.txt").write_text("b")

        result = FileOperations.list_directory(temp_dir)

        assert result.status == "success"
        assert isinstance(result.output["items"], list)
        names = {item["name"] for item in result.output["items"]}
        assert {"a.txt", "b.txt"} <= names


@pytest.mark.asyncio
async def test_tool_wrappers_use_file_ops():
    with tempfile.TemporaryDirectory(dir="/tmp") as temp_dir:
        path = os.path.join(temp_dir, "tool.txt")
        write_tool = WriteFileTool()
        move_tool = MoveFileTool()
        delete_tool = DeleteFileTool()

        write_result = await write_tool.execute(path=path, content="via tool")
        assert write_result.success

        move_target = os.path.join(temp_dir, "moved.txt")
        move_result = await move_tool.execute(source=path, destination=move_target)
        assert move_result.success
        assert os.path.exists(move_target)

        delete_result = await delete_tool.execute(path=move_target)
        assert delete_result.status == "success"
        assert not os.path.exists(move_target)


def test_response_formatter_produces_clean_text():
    with tempfile.TemporaryDirectory(dir="/tmp") as temp_dir:
        target = Path(temp_dir) / "clean.txt"
        result = FileOperations.write_file(str(target), "content")
        formatted = ResponseFormatter.format_tool_result(result)
        assert "`" not in formatted
        assert "clean.txt" in formatted
