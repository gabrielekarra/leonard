"""
Unit tests for the conversation context and entity resolution system.

Tests cover:
- Entity creation and storage
- Reference resolution (pronouns, ordinals, partial names)
- Selection tracking
- Confidence scoring
- Disambiguation handling
"""

import os
import tempfile
import pytest
from datetime import datetime

from leonard.context.entities import (
    Entity,
    EntityKind,
    EntityProvenance,
    EntityMetadata,
    EntityStore,
)
from leonard.context.resolver import (
    ReferenceResolver,
    ResolvedReference,
    ResolutionConfidence,
)
from leonard.context.conversation import ConversationContext


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    os.unlink(db_path)


@pytest.fixture
def entity_store(temp_db):
    """Create an entity store with temporary database."""
    return EntityStore(db_path=temp_db)


@pytest.fixture
def conversation_context(entity_store):
    """Create a conversation context for testing."""
    return ConversationContext(
        conversation_id="test-conv-1",
        store=entity_store,
    )


class TestEntity:
    """Tests for Entity dataclass."""

    def test_create_entity(self):
        """Test creating a new entity."""
        entity = Entity.create(
            path="/tmp/test/report.pdf",
            kind=EntityKind.FILE,
            provenance=EntityProvenance.USER_EXPLICIT,
            turn_index=1,
        )

        assert entity.id is not None
        assert entity.display_name == "report.pdf"
        assert entity.absolute_path.endswith("report.pdf")
        assert entity.kind == EntityKind.FILE
        assert entity.provenance == EntityProvenance.USER_EXPLICIT
        assert entity.turn_index == 1

    def test_create_entity_with_custom_name(self):
        """Test creating entity with custom display name."""
        entity = Entity.create(
            path="/tmp/test/data.json",
            kind=EntityKind.FILE,
            provenance=EntityProvenance.TOOL_OUTPUT,
            turn_index=2,
            display_name="API Response",
        )

        assert entity.display_name == "API Response"

    def test_create_selection(self):
        """Test creating a selection entity from multiple entities."""
        entities = [
            Entity.create("/tmp/file1.txt", EntityKind.FILE, EntityProvenance.LIST_RESULT, 1),
            Entity.create("/tmp/file2.txt", EntityKind.FILE, EntityProvenance.LIST_RESULT, 1),
            Entity.create("/tmp/file3.txt", EntityKind.FILE, EntityProvenance.LIST_RESULT, 1),
        ]

        selection = Entity.create_selection(entities, turn_index=1)

        assert selection.kind == EntityKind.SELECTION
        assert len(selection.selection_ids) == 3
        assert selection.metadata.item_count == 3

    def test_matches_name_exact(self):
        """Test exact name matching."""
        entity = Entity.create("/tmp/report.pdf", EntityKind.FILE, EntityProvenance.LIST_RESULT, 1)

        assert entity.matches_name("report.pdf") is True
        assert entity.matches_name("REPORT.PDF") is True  # Case insensitive
        assert entity.matches_name("report") is True  # Stem match
        assert entity.matches_name("other.pdf") is False

    def test_matches_name_partial(self):
        """Test partial name matching."""
        entity = Entity.create("/tmp/annual_report_2024.pdf", EntityKind.FILE, EntityProvenance.LIST_RESULT, 1)

        assert entity.matches_name("report") is True
        assert entity.matches_name("2024") is True
        assert entity.matches_name("annual") is True
        assert entity.matches_name("quarterly") is False

    def test_to_dict_from_dict(self):
        """Test serialization and deserialization."""
        original = Entity.create(
            path="/tmp/test.txt",
            kind=EntityKind.FILE,
            provenance=EntityProvenance.TOOL_OUTPUT,
            turn_index=5,
            metadata=EntityMetadata(size=1024, mtime=1234567890.0),
        )

        data = original.to_dict()
        restored = Entity.from_dict(data)

        assert restored.id == original.id
        assert restored.display_name == original.display_name
        assert restored.absolute_path == original.absolute_path
        assert restored.kind == original.kind
        assert restored.metadata.size == 1024


class TestEntityStore:
    """Tests for EntityStore."""

    def test_add_and_get(self, entity_store):
        """Test adding and retrieving an entity."""
        entity = Entity.create("/tmp/test.txt", EntityKind.FILE, EntityProvenance.USER_EXPLICIT, 1)

        entity_store.add("conv-1", entity)
        retrieved = entity_store.get(entity.id)

        assert retrieved is not None
        assert retrieved.id == entity.id
        assert retrieved.display_name == "test.txt"

    def test_get_by_path(self, entity_store):
        """Test retrieving entity by path."""
        entity = Entity.create("/tmp/unique-file.txt", EntityKind.FILE, EntityProvenance.USER_EXPLICIT, 1)
        entity_store.add("conv-1", entity)

        retrieved = entity_store.get_by_path("conv-1", "/tmp/unique-file.txt")

        assert retrieved is not None
        assert retrieved.id == entity.id

    def test_get_all(self, entity_store):
        """Test retrieving all entities for a conversation."""
        entities = [
            Entity.create(f"/tmp/file{i}.txt", EntityKind.FILE, EntityProvenance.LIST_RESULT, i)
            for i in range(5)
        ]

        for e in entities:
            entity_store.add("conv-1", e)

        all_entities = entity_store.get_all("conv-1")
        assert len(all_entities) == 5

    def test_get_recent(self, entity_store):
        """Test retrieving recent entities with limit."""
        for i in range(10):
            e = Entity.create(f"/tmp/file{i}.txt", EntityKind.FILE, EntityProvenance.LIST_RESULT, i)
            entity_store.add("conv-1", e)

        recent = entity_store.get_recent("conv-1", limit=3)
        assert len(recent) == 3

    def test_get_recent_by_kind(self, entity_store):
        """Test filtering recent entities by kind."""
        entity_store.add("conv-1", Entity.create("/tmp/file.txt", EntityKind.FILE, EntityProvenance.LIST_RESULT, 1))
        entity_store.add("conv-1", Entity.create("/tmp/folder", EntityKind.FOLDER, EntityProvenance.LIST_RESULT, 2))
        entity_store.add("conv-1", Entity.create("/tmp/file2.txt", EntityKind.FILE, EntityProvenance.LIST_RESULT, 3))

        files = entity_store.get_recent("conv-1", kind=EntityKind.FILE)
        folders = entity_store.get_recent("conv-1", kind=EntityKind.FOLDER)

        assert len(files) == 2
        assert len(folders) == 1

    def test_clear_conversation(self, entity_store):
        """Test clearing all entities for a conversation."""
        entity_store.add("conv-1", Entity.create("/tmp/file1.txt", EntityKind.FILE, EntityProvenance.LIST_RESULT, 1))
        entity_store.add("conv-1", Entity.create("/tmp/file2.txt", EntityKind.FILE, EntityProvenance.LIST_RESULT, 2))
        entity_store.add("conv-2", Entity.create("/tmp/file3.txt", EntityKind.FILE, EntityProvenance.LIST_RESULT, 1))

        entity_store.clear_conversation("conv-1")

        assert len(entity_store.get_all("conv-1")) == 0
        assert len(entity_store.get_all("conv-2")) == 1

    def test_last_active_file(self, entity_store):
        """Test last active file tracking."""
        file1 = Entity.create("/tmp/file1.txt", EntityKind.FILE, EntityProvenance.TOOL_READ, 1)
        file2 = Entity.create("/tmp/file2.txt", EntityKind.FILE, EntityProvenance.TOOL_READ, 2)

        entity_store.add("conv-1", file1)
        entity_store.add("conv-1", file2)

        entity_store.set_last_active_file("conv-1", file1.id)
        assert entity_store.get_last_active_file("conv-1").id == file1.id

        entity_store.set_last_active_file("conv-1", file2.id)
        assert entity_store.get_last_active_file("conv-1").id == file2.id

    def test_turn_index(self, entity_store):
        """Test turn index tracking."""
        assert entity_store.get_turn_index("conv-1") == 0

        new_index = entity_store.increment_turn("conv-1")
        assert new_index == 1
        assert entity_store.get_turn_index("conv-1") == 1

        entity_store.increment_turn("conv-1")
        entity_store.increment_turn("conv-1")
        assert entity_store.get_turn_index("conv-1") == 3


class TestReferenceResolver:
    """Tests for ReferenceResolver."""

    @pytest.fixture
    def resolver(self, entity_store):
        return ReferenceResolver(entity_store)

    def test_resolve_explicit_path(self, resolver, entity_store):
        """Test resolving explicit path in message."""
        entity = Entity.create("/tmp/explicit.txt", EntityKind.FILE, EntityProvenance.USER_EXPLICIT, 1)
        entity_store.add("conv-1", entity)

        result = resolver.resolve("conv-1", "read /tmp/explicit.txt")

        assert result.confidence == ResolutionConfidence.HIGH
        assert result.score == 1.0

    def test_resolve_pronoun_it(self, resolver, entity_store):
        """Test resolving 'it' pronoun to last active file."""
        file = Entity.create("/tmp/recent.txt", EntityKind.FILE, EntityProvenance.TOOL_READ, 1)
        entity_store.add("conv-1", file)
        entity_store.set_last_active_file("conv-1", file.id)

        result = resolver.resolve("conv-1", "delete it")

        assert result.entity is not None
        assert result.entity.id == file.id
        assert result.confidence in (ResolutionConfidence.HIGH, ResolutionConfidence.MEDIUM)

    def test_resolve_pronoun_that_file(self, resolver, entity_store):
        """Test resolving 'that file' to last active file."""
        file = Entity.create("/tmp/target.pdf", EntityKind.FILE, EntityProvenance.TOOL_READ, 1)
        entity_store.add("conv-1", file)
        entity_store.set_last_active_file("conv-1", file.id)

        result = resolver.resolve("conv-1", "open that file")

        assert result.entity is not None
        assert result.entity.display_name == "target.pdf"

    def test_resolve_pronoun_the_folder(self, resolver, entity_store):
        """Test resolving 'the folder' to last active folder."""
        folder = Entity.create("/tmp/documents", EntityKind.FOLDER, EntityProvenance.LIST_RESULT, 1)
        entity_store.add("conv-1", folder)
        entity_store.set_last_active_folder("conv-1", folder.id)

        result = resolver.resolve("conv-1", "list the folder")

        assert result.entity is not None
        assert result.entity.kind == EntityKind.FOLDER

    def test_resolve_ordinal_first(self, resolver, entity_store):
        """Test resolving 'first' ordinal from selection."""
        items = [
            Entity.create(f"/tmp/file{i}.txt", EntityKind.FILE, EntityProvenance.LIST_RESULT, 1)
            for i in range(3)
        ]
        for item in items:
            entity_store.add("conv-1", item)

        selection = Entity.create_selection(items, turn_index=1)
        entity_store.add("conv-1", selection)
        entity_store.set_current_selection("conv-1", selection.id)

        result = resolver.resolve("conv-1", "delete the first")

        assert result.entity is not None
        assert result.entity.id == items[0].id
        assert result.confidence == ResolutionConfidence.HIGH

    def test_resolve_ordinal_second(self, resolver, entity_store):
        """Test resolving 'second' ordinal."""
        items = [
            Entity.create(f"/tmp/doc{i}.pdf", EntityKind.FILE, EntityProvenance.LIST_RESULT, 1)
            for i in range(5)
        ]
        for item in items:
            entity_store.add("conv-1", item)

        selection = Entity.create_selection(items, turn_index=1)
        entity_store.add("conv-1", selection)
        entity_store.set_current_selection("conv-1", selection.id)

        result = resolver.resolve("conv-1", "open the second one")

        assert result.entity is not None
        assert result.entity.id == items[1].id

    def test_resolve_ordinal_last(self, resolver, entity_store):
        """Test resolving 'last' ordinal."""
        items = [
            Entity.create(f"/tmp/item{i}.txt", EntityKind.FILE, EntityProvenance.LIST_RESULT, 1)
            for i in range(4)
        ]
        for item in items:
            entity_store.add("conv-1", item)

        selection = Entity.create_selection(items, turn_index=1)
        entity_store.add("conv-1", selection)
        entity_store.set_current_selection("conv-1", selection.id)

        result = resolver.resolve("conv-1", "delete the last")

        assert result.entity is not None
        assert result.entity.id == items[-1].id

    def test_resolve_by_partial_name(self, resolver, entity_store):
        """Test resolving by partial name match."""
        entity_store.add("conv-1", Entity.create("/tmp/report_2024.pdf", EntityKind.FILE, EntityProvenance.LIST_RESULT, 1))
        entity_store.add("conv-1", Entity.create("/tmp/data.csv", EntityKind.FILE, EntityProvenance.LIST_RESULT, 1))

        result = resolver.resolve("conv-1", "open the report")

        assert result.entity is not None
        assert "report" in result.entity.display_name.lower()

    def test_resolve_ambiguous_multiple_matches(self, resolver, entity_store):
        """Test handling ambiguous references with multiple matches."""
        entity_store.add("conv-1", Entity.create("/tmp/report_q1.pdf", EntityKind.FILE, EntityProvenance.LIST_RESULT, 1))
        entity_store.add("conv-1", Entity.create("/tmp/report_q2.pdf", EntityKind.FILE, EntityProvenance.LIST_RESULT, 1))
        entity_store.add("conv-1", Entity.create("/tmp/report_q3.pdf", EntityKind.FILE, EntityProvenance.LIST_RESULT, 1))

        # Use "the report" pattern which the resolver extracts as a name
        result = resolver.resolve("conv-1", "delete the report")

        assert result.confidence == ResolutionConfidence.AMBIGUOUS
        assert len(result.alternatives) >= 2

    def test_resolve_no_match(self, resolver, entity_store):
        """Test handling no matches."""
        result = resolver.resolve("conv-1", "delete nonexistent.txt")

        assert result.entity is None
        assert result.confidence == ResolutionConfidence.NONE

    def test_requires_confirmation_destructive(self, resolver, entity_store):
        """Test that destructive actions on pronouns require confirmation."""
        file = Entity.create("/tmp/important.txt", EntityKind.FILE, EntityProvenance.TOOL_READ, 1)
        entity_store.add("conv-1", file)
        entity_store.set_last_active_file("conv-1", file.id)

        result = resolver.resolve("conv-1", "delete it", is_destructive=True)

        # Should still resolve but with lower confidence
        assert result.entity is not None
        assert resolver.requires_confirmation(result, "delete_file") is True


class TestConversationContext:
    """Tests for ConversationContext."""

    def test_track_entity(self, conversation_context):
        """Test tracking a new entity."""
        entity = conversation_context.track_entity(
            path="/tmp/test.txt",
            kind=EntityKind.FILE,
            provenance=EntityProvenance.USER_EXPLICIT,
        )

        assert entity.id is not None
        assert entity.display_name == "test.txt"

        # Should be set as last active
        last_active = conversation_context.get_last_active_file()
        assert last_active.id == entity.id

    def test_track_duplicate_returns_existing(self, conversation_context):
        """Test that tracking same path returns existing entity."""
        e1 = conversation_context.track_entity("/tmp/dup.txt", EntityKind.FILE, EntityProvenance.USER_EXPLICIT)
        e2 = conversation_context.track_entity("/tmp/dup.txt", EntityKind.FILE, EntityProvenance.TOOL_READ)

        assert e1.id == e2.id

    def test_resolve_reference(self, conversation_context):
        """Test resolving a reference."""
        conversation_context.track_entity("/tmp/myfile.txt", EntityKind.FILE, EntityProvenance.TOOL_READ)

        result = conversation_context.resolve("delete it")

        assert result.entity is not None

    def test_confirmation_flow(self, conversation_context):
        """Test confirmation/cancellation detection."""
        assert conversation_context.is_confirmation("yes") is True
        assert conversation_context.is_confirmation("ok") is True
        assert conversation_context.is_confirmation("sì") is True

        assert conversation_context.is_cancellation("no") is True
        assert conversation_context.is_cancellation("cancel") is True
        assert conversation_context.is_cancellation("nevermind") is True

        assert conversation_context.is_confirmation("no") is False
        assert conversation_context.is_cancellation("yes") is False

    def test_pending_action(self, conversation_context):
        """Test pending action management."""
        entity = conversation_context.track_entity("/tmp/pending.txt", EntityKind.FILE, EntityProvenance.USER_EXPLICIT)

        conversation_context.set_pending_action(
            tool_name="delete_file",
            params={"path": "/tmp/pending.txt"},
            entity=entity,
            reason="Confirmation required for delete",
        )

        pending = conversation_context.get_pending_action()
        assert pending is not None
        assert pending.tool_name == "delete_file"
        assert pending.entity.id == entity.id

        cleared = conversation_context.clear_pending_action()
        assert cleared is not None
        assert conversation_context.get_pending_action() is None

    def test_selection_tracking(self, conversation_context):
        """Test selection tracking from list results."""
        # Track multiple entities
        entities = []
        for i in range(5):
            e = conversation_context.track_entity(
                f"/tmp/item{i}.txt",
                EntityKind.FILE,
                EntityProvenance.LIST_RESULT,
                set_active=False,
            )
            entities.append(e)

        # No selection yet
        assert conversation_context.get_current_selection() is None

        # Manually create selection (normally done by track_from_tool_result)
        selection = Entity.create_selection(entities, turn_index=conversation_context.turn_index)
        conversation_context.store.add(conversation_context.conversation_id, selection)
        conversation_context.store.set_current_selection(conversation_context.conversation_id, selection.id)

        # Now we have a selection
        sel = conversation_context.get_current_selection()
        assert sel is not None
        assert sel.kind == EntityKind.SELECTION

        items = conversation_context.get_selection_items()
        assert len(items) == 5

    def test_turn_tracking(self, conversation_context):
        """Test conversation turn tracking."""
        assert conversation_context.turn_index == 0

        conversation_context.next_turn()
        assert conversation_context.turn_index == 1

        conversation_context.next_turn()
        conversation_context.next_turn()
        assert conversation_context.turn_index == 3

    def test_clear(self, conversation_context):
        """Test clearing conversation context."""
        conversation_context.track_entity("/tmp/clear_test.txt", EntityKind.FILE, EntityProvenance.USER_EXPLICIT)
        conversation_context.set_pending_action("delete_file", {}, None, "test")

        conversation_context.clear()

        assert len(conversation_context.get_recent_entities()) == 0
        assert conversation_context.get_pending_action() is None


class TestResolvedReference:
    """Tests for ResolvedReference dataclass."""

    def test_is_confident(self):
        """Test confidence checking."""
        high = ResolvedReference(None, ResolutionConfidence.HIGH, 0.95, "test", [])
        medium = ResolvedReference(None, ResolutionConfidence.MEDIUM, 0.75, "test", [])
        low = ResolvedReference(None, ResolutionConfidence.LOW, 0.4, "test", [])
        ambig = ResolvedReference(None, ResolutionConfidence.AMBIGUOUS, 0.8, "test", [])

        assert high.is_confident is True
        assert medium.is_confident is True
        assert low.is_confident is False
        assert ambig.is_confident is False

    def test_needs_confirmation(self):
        """Test confirmation need detection."""
        low = ResolvedReference(None, ResolutionConfidence.LOW, 0.4, "test", [])
        ambig = ResolvedReference(None, ResolutionConfidence.AMBIGUOUS, 0.8, "test", [])
        high = ResolvedReference(None, ResolutionConfidence.HIGH, 0.95, "test", [])

        assert low.needs_confirmation is True
        assert ambig.needs_confirmation is True
        assert high.needs_confirmation is False

    def test_format_disambiguation_single(self):
        """Test disambiguation formatting for single alternative."""
        entity = Entity.create("/tmp/single.txt", EntityKind.FILE, EntityProvenance.LIST_RESULT, 1)
        ref = ResolvedReference(None, ResolutionConfidence.LOW, 0.4, "test", [entity])

        formatted = ref.format_disambiguation()

        assert "single.txt" in formatted
        assert "Did you mean" in formatted

    def test_format_disambiguation_multiple(self):
        """Test disambiguation formatting for multiple alternatives."""
        entities = [
            Entity.create(f"/tmp/option{i}.txt", EntityKind.FILE, EntityProvenance.LIST_RESULT, 1)
            for i in range(3)
        ]
        ref = ResolvedReference(None, ResolutionConfidence.AMBIGUOUS, 0.7, "test", entities)

        formatted = ref.format_disambiguation()

        assert "Which file" in formatted
        assert "1." in formatted
        assert "2." in formatted
        assert "3." in formatted
