"""
Conversation context manager for chat-aware operations.

Provides a high-level interface for managing entity tracking across
a conversation, coordinating the entity store and reference resolver.
"""

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from leonard.context.entities import (
    Entity,
    EntityKind,
    EntityMetadata,
    EntityProvenance,
    EntityStore,
)
from leonard.context.resolver import (
    ReferenceResolver,
    ResolvedReference,
    ResolutionConfidence,
)
from leonard.tools.base import ToolResult


@dataclass
class PendingAction:
    """An action waiting for user confirmation."""
    tool_name: str
    params: dict
    entity: Optional[Entity]
    reason: str  # Why confirmation is needed
    timestamp: datetime = field(default_factory=datetime.now)


class ConversationContext:
    """
    Manages entity tracking and reference resolution for a single conversation.

    This is the main interface for chat-aware file operations. It:
    - Tracks files/folders mentioned or created during conversation
    - Resolves user references ("it", "that file", "the second one")
    - Manages selection sets from list/search operations
    - Handles confirmation flows for destructive operations
    """

    def __init__(
        self,
        conversation_id: Optional[str] = None,
        store: Optional[EntityStore] = None,
    ):
        """
        Initialize conversation context.

        Args:
            conversation_id: Unique ID for this conversation. Generated if not provided.
            store: Entity store instance. Creates new one if not provided.
        """
        self.conversation_id = conversation_id or str(uuid.uuid4())
        self.store = store or EntityStore()
        self.resolver = ReferenceResolver(self.store)
        self._pending_action: Optional[PendingAction] = None

    @property
    def turn_index(self) -> int:
        """Current conversation turn index."""
        return self.store.get_turn_index(self.conversation_id)

    def next_turn(self) -> int:
        """Advance to next turn and return the new index."""
        return self.store.increment_turn(self.conversation_id)

    # --- Entity Tracking ---

    def track_entity(
        self,
        path: str,
        kind: EntityKind,
        provenance: EntityProvenance,
        display_name: Optional[str] = None,
        metadata: Optional[EntityMetadata] = None,
        set_active: bool = True,
    ) -> Entity:
        """
        Track a new entity in the conversation.

        Args:
            path: Absolute or relative path to the file/folder
            kind: FILE or FOLDER
            provenance: How the entity was introduced
            display_name: Optional human-readable name
            metadata: Optional file metadata
            set_active: If True, set as last active file/folder

        Returns:
            The created Entity
        """
        # Check if entity already tracked
        existing = self.store.get_by_path(self.conversation_id, path)
        if existing:
            # Update provenance if more specific
            if provenance != EntityProvenance.INFERRED:
                existing.provenance = provenance
                existing.timestamp = datetime.now()
                self.store.update(existing)
            if set_active:
                self._set_active(existing)
            return existing

        entity = Entity.create(
            path=path,
            kind=kind,
            provenance=provenance,
            turn_index=self.turn_index,
            display_name=display_name,
            metadata=metadata,
        )

        self.store.add(self.conversation_id, entity)

        if set_active:
            self._set_active(entity)

        return entity

    def track_from_tool_result(self, result: ToolResult) -> list[Entity]:
        """
        Track entities from a tool execution result.

        Automatically extracts entities from various tool outputs.
        Returns list of tracked entities.
        """
        entities = []
        action = result.action or ""

        # List directory -> create selection
        if action == "list" and isinstance(result.output, dict):
            entities = self._track_list_result(result.output)

        # Create/write file (handle both "create" and "write" actions)
        elif action in ("create", "write", "append"):
            paths = result.after_paths or result.changed
            for path in paths:
                e = self.track_entity(
                    path=path,
                    kind=EntityKind.FILE,
                    provenance=EntityProvenance.TOOL_OUTPUT,
                )
                entities.append(e)

        # Read file
        elif action == "read":
            paths = []
            if isinstance(result.output, dict) and result.output.get("path"):
                paths.append(result.output["path"])
            paths = paths or result.before_paths or result.changed
            for path in paths:
                e = self.track_entity(
                    path=path,
                    kind=EntityKind.FILE,
                    provenance=EntityProvenance.TOOL_READ,
                )
                entities.append(e)

        # Move/rename
        elif action == "move":
            dests = result.after_paths or (result.changed[-1:] if result.changed else [])
            for dest in dests:
                e = self.track_entity(
                    path=dest,
                    kind=EntityKind.FILE,
                    provenance=EntityProvenance.TOOL_MOVE,
                )
                entities.append(e)

        # Copy
        elif action == "copy":
            dests = result.after_paths or (result.changed[-1:] if result.changed else [])
            for dest in dests:
                e = self.track_entity(
                    path=dest,
                    kind=EntityKind.FILE,
                    provenance=EntityProvenance.TOOL_COPY,
                )
                entities.append(e)

        # Search results
        elif action == "search" and isinstance(result.output, dict):
            matches = result.output.get("matches", [])
            for match in matches:
                path = match.get("path") if isinstance(match, dict) else match
                if path:
                    e = self.track_entity(
                        path=path,
                        kind=EntityKind.FILE,
                        provenance=EntityProvenance.SEARCH_RESULT,
                        set_active=False,
                    )
                    entities.append(e)
            if entities:
                self._create_selection(entities)

        # Create directory
        elif action in ("create_directory", "mkdir", "create"):
            paths = result.after_paths or result.changed
            for path in paths:
                e = self.track_entity(
                    path=path,
                    kind=EntityKind.FOLDER,
                    provenance=EntityProvenance.TOOL_OUTPUT,
                )
                entities.append(e)
        elif action == "delete" and result.before_paths:
            for path in result.before_paths:
                existing = self.store.get_by_path(self.conversation_id, path)
                if existing:
                    self.remove_entity(existing.id)

        return entities

    def _track_list_result(self, output: dict) -> list[Entity]:
        """Track entities from list_directory output."""
        entities = []
        base_path = output.get("path", "")
        items = output.get("items", [])

        for item in items:
            if isinstance(item, dict):
                name = item.get("name", "")
                item_type = item.get("type")
                is_dir = item.get("is_dir", False) or item_type == "dir"
                size = item.get("size") or item.get("size_bytes")
            else:
                name = str(item)
                is_dir = False
                size = None

            if not name:
                continue

            full_path = os.path.join(base_path, name)
            kind = EntityKind.FOLDER if is_dir else EntityKind.FILE
            metadata = EntityMetadata(size=size) if size else None

            e = self.track_entity(
                path=full_path,
                kind=kind,
                provenance=EntityProvenance.LIST_RESULT,
                display_name=name,
                metadata=metadata,
                set_active=False,
            )
            entities.append(e)

        # Track the folder itself
        if base_path:
            folder_entity = self.track_entity(
                path=base_path,
                kind=EntityKind.FOLDER,
                provenance=EntityProvenance.LIST_RESULT,
                set_active=True,
            )

        # Create selection from items
        if entities:
            self._create_selection(entities)

        return entities

    def _create_selection(self, entities: list[Entity]) -> Entity:
        """Create a selection entity from a list of entities."""
        selection = Entity.create_selection(
            entities=entities,
            turn_index=self.turn_index,
        )
        self.store.add(self.conversation_id, selection)
        self.store.set_current_selection(self.conversation_id, selection.id)
        return selection

    def _set_active(self, entity: Entity) -> None:
        """Set entity as last active file or folder."""
        if entity.kind == EntityKind.FILE:
            self.store.set_last_active_file(self.conversation_id, entity.id)
        elif entity.kind == EntityKind.FOLDER:
            self.store.set_last_active_folder(self.conversation_id, entity.id)

    # --- Reference Resolution ---

    def resolve(
        self,
        utterance: str,
        preferred_kind: Optional[EntityKind] = None,
        is_destructive: bool = False,
    ) -> ResolvedReference:
        """
        Resolve a user reference to an entity.

        Args:
            utterance: User's message
            preferred_kind: Prefer FILE or FOLDER
            is_destructive: If True, require higher confidence

        Returns:
            ResolvedReference with entity and confidence
        """
        return self.resolver.resolve(
            conversation_id=self.conversation_id,
            utterance=utterance,
            preferred_kind=preferred_kind,
            is_destructive=is_destructive,
        )

    def resolve_for_action(self, utterance: str, action: str) -> ResolvedReference:
        """
        Resolve reference with action-specific logic.

        Automatically handles destructive action requirements.
        """
        return self.resolver.resolve_for_action(
            conversation_id=self.conversation_id,
            utterance=utterance,
            action=action,
        )

    def needs_confirmation(
        self,
        resolution: ResolvedReference,
        action: str,
    ) -> bool:
        """Check if action needs user confirmation given the resolution."""
        return self.resolver.requires_confirmation(resolution, action)

    # --- Confirmation Flow ---

    def set_pending_action(
        self,
        tool_name: str,
        params: dict,
        entity: Optional[Entity],
        reason: str,
    ) -> None:
        """Store a pending action awaiting confirmation."""
        self._pending_action = PendingAction(
            tool_name=tool_name,
            params=params,
            entity=entity,
            reason=reason,
        )

    def get_pending_action(self) -> Optional[PendingAction]:
        """Get the pending action if any."""
        return self._pending_action

    def clear_pending_action(self) -> Optional[PendingAction]:
        """Clear and return the pending action."""
        action = self._pending_action
        self._pending_action = None
        return action

    def is_confirmation(self, message: str) -> bool:
        """Check if message is a confirmation."""
        confirmations = {
            "yes", "y", "ok", "sure", "do it", "proceed", "confirm",
            "sì", "si", "vai", "fallo", "conferma", "procedi",
        }
        return message.lower().strip() in confirmations

    def is_cancellation(self, message: str) -> bool:
        """Check if message is a cancellation."""
        cancellations = {
            "no", "n", "cancel", "stop", "abort", "nevermind", "never mind",
            "annulla", "no grazie", "ferma",
        }
        return message.lower().strip() in cancellations

    # --- Entity Queries ---

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get entity by ID."""
        return self.store.get(entity_id)

    def get_entity_by_path(self, path: str) -> Optional[Entity]:
        """Get entity by path."""
        return self.store.get_by_path(self.conversation_id, path)

    def get_last_active_file(self) -> Optional[Entity]:
        """Get the last active file entity."""
        return self.store.get_last_active_file(self.conversation_id)

    def get_last_active_folder(self) -> Optional[Entity]:
        """Get the last active folder entity."""
        return self.store.get_last_active_folder(self.conversation_id)

    def get_current_selection(self) -> Optional[Entity]:
        """Get the current selection entity."""
        return self.store.get_current_selection(self.conversation_id)

    def get_selection_items(self) -> list[Entity]:
        """Get entities in the current selection."""
        selection = self.get_current_selection()
        if selection:
            return self.store.get_selection_items(self.conversation_id, selection.id)
        return []

    def get_recent_entities(
        self,
        kind: Optional[EntityKind] = None,
        limit: int = 10,
    ) -> list[Entity]:
        """Get recent entities, optionally filtered by kind."""
        return self.store.get_recent(self.conversation_id, kind=kind, limit=limit)

    # --- Cleanup ---

    def clear(self) -> None:
        """Clear all entities and state for this conversation."""
        self.store.clear_conversation(self.conversation_id)
        self._pending_action = None

    def remove_entity(self, entity_id: str) -> None:
        """Remove a specific entity (e.g., after deletion)."""
        self.store.remove(entity_id)

    # --- Verification ---

    def verify_entity_exists(self, entity: Entity) -> bool:
        """Verify that an entity still exists on the filesystem."""
        exists = os.path.exists(entity.absolute_path)
        entity.verified_exists = exists
        self.store.update(entity)
        return exists

    def update_entity_path(self, entity: Entity, new_path: str) -> Entity:
        """Update entity path after move/rename operation."""
        entity.absolute_path = os.path.realpath(os.path.expanduser(new_path))
        entity.display_name = os.path.basename(entity.absolute_path)
        entity.provenance = EntityProvenance.TOOL_MOVE
        entity.timestamp = datetime.now()
        self.store.update(entity)
        return entity
