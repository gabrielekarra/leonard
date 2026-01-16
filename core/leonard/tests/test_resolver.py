import os
import tempfile
from pathlib import Path

from leonard.context import ConversationContext, EntityKind, EntityProvenance
from leonard.tools.file_ops import FileOperations


def _make_context():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    from leonard.context.entities import EntityStore
    store = EntityStore(db_path=db_path)
    return ConversationContext(conversation_id="resolver-test", store=store), db_path


def test_pronoun_resolves_last_active_file():
    context, db_path = _make_context()
    try:
        context.track_entity("/tmp/alpha.txt", EntityKind.FILE, EntityProvenance.USER_EXPLICIT)
        resolution = context.resolve("delete it")
        assert resolution.entity is not None
        assert resolution.entity.display_name == "alpha.txt"
    finally:
        os.unlink(db_path)


def test_ordinal_resolves_selection():
    context, db_path = _make_context()
    with tempfile.TemporaryDirectory(dir="/tmp") as temp_dir:
        try:
            Path(temp_dir, "one.txt").touch()
            Path(temp_dir, "two.txt").touch()
            list_result = FileOperations.list_directory(path=temp_dir)
            context.next_turn()
            context.track_from_tool_result(list_result)

            resolution = context.resolve("delete the second one")
            assert resolution.entity is not None
            assert resolution.entity.display_name in {"one.txt", "two.txt"}
        finally:
            os.unlink(db_path)


def test_partial_name_match():
    context, db_path = _make_context()
    try:
        context.track_entity("/tmp/report-final.pdf", EntityKind.FILE, EntityProvenance.USER_EXPLICIT)
        context.track_entity("/tmp/report-draft.pdf", EntityKind.FILE, EntityProvenance.USER_EXPLICIT)
        resolution = context.resolve("delete report-final")
        assert resolution.entity is not None
        assert resolution.entity.display_name == "report-final.pdf"
    finally:
        os.unlink(db_path)
