import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from leonard.engine.orchestrator import LeonardOrchestrator
from leonard.tools.executor import ToolExecutor


@pytest.fixture
def temp_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("leonard", dir="/tmp")


@pytest.mark.asyncio
async def test_executor_runs_with_verification(temp_dir):
    executor = ToolExecutor()
    target = os.path.join(temp_dir, "listed")
    os.makedirs(target, exist_ok=True)
    PathA = os.path.join(target, "a.txt")
    PathB = os.path.join(target, "b.txt")
    open(PathA, "w").write("a")
    open(PathB, "w").write("b")

    result = await executor.execute("list_directory", {"path": target})

    assert result.success
    assert result.verification.passed
    assert len(result.output["items"]) >= 2


@pytest.mark.asyncio
async def test_orchestrator_tool_flow_returns_verified_response(temp_dir):
    orch = LeonardOrchestrator(tools_enabled=True, rag_enabled=False)
    orch._initialized = True
    orch.process_manager.is_running = MagicMock(return_value=True)
    orch.router.route = AsyncMock()
    orch.router.ensure_router_ready = AsyncMock()
    target = os.path.join(temp_dir, "note.txt")

    response = await orch.chat(f"create file {target} with content 'hello'")

    assert "note.txt" in response
    last_result = orch.get_last_tool_result()
    assert last_result["verification"]["passed"] is True
    assert os.path.exists(target)


@pytest.mark.asyncio
async def test_orchestrator_sanitizes_model_output():
    orch = LeonardOrchestrator(tools_enabled=False, rag_enabled=False)
    orch._initialized = True
    orch.process_manager.is_running = MagicMock(return_value=True)
    orch.process_manager.chat = AsyncMock(return_value='```json {"tool":"x"}``` Clean response')
    orch.router.route = AsyncMock(return_value=SimpleNamespace(model_id="test-model"))
    orch._ensure_model_ready = AsyncMock()

    response = await orch.chat("hello")

    assert "tool" not in response.lower()
    assert "Clean response" in response


def test_detect_tool_action_handles_list(temp_dir):
    orch = LeonardOrchestrator(tools_enabled=True, rag_enabled=False)
    orch._initialized = True
    message = f"list files in {temp_dir}"

    detected = orch._detect_tool_action(message)

    assert detected is not None
    tool_name, params = detected
    assert tool_name == "list_directory"
    assert params["path"] == temp_dir


def test_context_folder_resolution():
    orch = LeonardOrchestrator(tools_enabled=True, rag_enabled=False)
    orch._last_directory_context = {"path": "/tmp/Desktop", "items": ["Documents", "Images"]}

    detected = orch._detect_tool_action("delete the folder documents")

    assert detected is not None
    tool_name, params = detected
    assert tool_name == "delete_file"
    assert params["path"] == "/tmp/Desktop/Documents"


def test_delete_named_file_in_context():
    orch = LeonardOrchestrator(tools_enabled=True, rag_enabled=False)
    orch._last_directory_context = {"path": "/tmp/Desktop/Documents", "items": ["test.txt", "other.doc"]}

    detected = orch._detect_tool_action("delete the file called test.txt inside the documents folder")

    assert detected is not None
    tool_name, params = detected
    assert tool_name == "delete_file"
    assert params["path"] == "/tmp/Desktop/Documents/test.txt"


def test_delete_context_folder_without_redundant_name():
    orch = LeonardOrchestrator(tools_enabled=True, rag_enabled=False)
    orch._last_directory_context = {"path": "/tmp/Desktop/Documents", "items": ["test.txt"]}

    detected = orch._detect_tool_action("delete the folder documents")
    assert detected is not None
    tool_name, params = detected
    assert tool_name == "delete_file"
    assert params["path"] == "/tmp/Desktop/Documents"

    detected2 = orch._detect_tool_action("delete the folder")
    assert detected2 is not None
    tool_name2, params2 = detected2
    assert tool_name2 == "delete_file"
    assert params2["path"] == "/tmp/Desktop/Documents"


def test_rename_in_context():
    orch = LeonardOrchestrator(tools_enabled=True, rag_enabled=False)
    orch._last_directory_context = {"path": "/tmp/Desktop/Documents", "items": ["old.txt"]}

    detected = orch._detect_tool_action("rename old.txt to new.txt")
    assert detected is not None
    tool_name, params = detected
    assert tool_name == "move_file"
    assert params["source"] == "/tmp/Desktop/Documents/old.txt"
    assert params["destination"] == "/tmp/Desktop/Documents/new.txt"


def test_rename_without_extension_uses_source_extension():
    orch = LeonardOrchestrator(tools_enabled=True, rag_enabled=False)
    orch._last_directory_context = {"path": "/tmp/Desktop/Documents", "items": ["tessera-fif.pdf", "other.doc"]}

    detected = orch._detect_tool_action("rename tessera-fif to tessera")
    assert detected is not None
    tool_name, params = detected
    assert tool_name == "move_file"
    assert params["source"] == "/tmp/Desktop/Documents/tessera-fif.pdf"
    assert params["destination"] == "/tmp/Desktop/Documents/tessera.pdf"
