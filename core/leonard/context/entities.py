"""
Entity definitions and storage for conversation context.

An Entity represents a tracked file, folder, or selection that was mentioned
or created during a conversation. Entities have stable IDs so they can be
referenced reliably even across multiple tool operations.
"""

import os
import sqlite3
import uuid
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class EntityKind(str, Enum):
    """Type of tracked entity."""
    FILE = "file"
    FOLDER = "folder"
    SELECTION = "selection"  # Multiple files from search/list
    INDEX = "index"  # Indexed content reference
    TOOL_RESULT = "tool_result"  # Generic tool output


class EntityProvenance(str, Enum):
    """How the entity was introduced to the conversation."""
    USER_EXPLICIT = "user_explicit"  # User typed the path
    SEARCH_RESULT = "search_result"  # From search_files tool
    LIST_RESULT = "list_result"  # From list_directory tool
    TOOL_OUTPUT = "tool_output"  # Created by a tool (write_file, create_directory)
    TOOL_READ = "tool_read"  # Read by read_file tool
    TOOL_MOVE = "tool_move"  # Result of move/rename
    TOOL_COPY = "tool_copy"  # Result of copy
    INFERRED = "inferred"  # Inferred from conversation context


@dataclass
class EntityMetadata:
    """Optional metadata about an entity."""
    size: Optional[int] = None
    mtime: Optional[float] = None
    hash: Optional[str] = None
    mime_type: Optional[str] = None
    item_count: Optional[int] = None  # For folders/selections

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "EntityMetadata":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Entity:
    """
    A tracked entity in the conversation.

    Entities have stable UUIDs that persist across operations, so "it" can
    reliably refer to the same file even after rename/move.
    """
    id: str  # Stable UUID
    display_name: str  # Human-readable name (e.g., "report.pdf")
    absolute_path: str  # Canonical resolved path
    kind: EntityKind
    provenance: EntityProvenance
    timestamp: datetime
    turn_index: int  # Conversation turn when entity was introduced
    metadata: EntityMetadata = field(default_factory=EntityMetadata)

    # For selections: list of child entity IDs
    selection_ids: list[str] = field(default_factory=list)

    # Track if entity still exists on filesystem
    verified_exists: Optional[bool] = None

    def __post_init__(self):
        # Ensure path is canonical
        if self.absolute_path:
            self.absolute_path = os.path.realpath(os.path.expanduser(self.absolute_path))

    @classmethod
    def create(
        cls,
        path: str,
        kind: EntityKind,
        provenance: EntityProvenance,
        turn_index: int,
        display_name: Optional[str] = None,
        metadata: Optional[EntityMetadata] = None,
    ) -> "Entity":
        """Factory method to create a new entity with generated UUID."""
        abs_path = os.path.realpath(os.path.expanduser(path))
        name = display_name or os.path.basename(abs_path) or abs_path

        return cls(
            id=str(uuid.uuid4()),
            display_name=name,
            absolute_path=abs_path,
            kind=kind,
            provenance=provenance,
            timestamp=datetime.now(),
            turn_index=turn_index,
            metadata=metadata or EntityMetadata(),
        )

    @classmethod
    def create_selection(
        cls,
        entities: list["Entity"],
        turn_index: int,
        display_name: Optional[str] = None,
    ) -> "Entity":
        """Create a selection entity from multiple entities."""
        if not entities:
            raise ValueError("Selection must contain at least one entity")

        # Use parent directory as the "path" for the selection
        parent_dir = os.path.dirname(entities[0].absolute_path)
        name = display_name or f"Selection of {len(entities)} items"

        return cls(
            id=str(uuid.uuid4()),
            display_name=name,
            absolute_path=parent_dir,
            kind=EntityKind.SELECTION,
            provenance=EntityProvenance.LIST_RESULT,
            timestamp=datetime.now(),
            turn_index=turn_index,
            metadata=EntityMetadata(item_count=len(entities)),
            selection_ids=[e.id for e in entities],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "absolute_path": self.absolute_path,
            "kind": self.kind.value,
            "provenance": self.provenance.value,
            "timestamp": self.timestamp.isoformat(),
            "turn_index": self.turn_index,
            "metadata": self.metadata.to_dict(),
            "selection_ids": self.selection_ids,
            "verified_exists": self.verified_exists,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Entity":
        return cls(
            id=data["id"],
            display_name=data["display_name"],
            absolute_path=data["absolute_path"],
            kind=EntityKind(data["kind"]),
            provenance=EntityProvenance(data["provenance"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            turn_index=data["turn_index"],
            metadata=EntityMetadata.from_dict(data.get("metadata", {})),
            selection_ids=data.get("selection_ids", []),
            verified_exists=data.get("verified_exists"),
        )

    def matches_name(self, query: str) -> bool:
        """Check if this entity matches a name query."""
        query_lower = query.lower().strip()
        name_lower = self.display_name.lower()
        stem = os.path.splitext(self.display_name)[0].lower()

        # Exact match
        if query_lower == name_lower:
            return True

        # Stem match (e.g., "report" matches "report.pdf")
        if query_lower == stem:
            return True

        # Partial match (e.g., "report" in "annual_report.pdf")
        if query_lower in name_lower or query_lower in stem:
            return True

        return False


class EntityStore:
    """
    SQLite-backed persistent storage for entities.

    Keyed by conversation_id, allowing multiple concurrent conversations
    with independent entity tracking.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the entity store.

        Args:
            db_path: Path to SQLite database. Defaults to ~/.leonard/entities.db
        """
        if db_path is None:
            leonard_dir = Path.home() / ".leonard"
            leonard_dir.mkdir(exist_ok=True)
            db_path = str(leonard_dir / "entities.db")

        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversation
                ON entities(conversation_id)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_state (
                    conversation_id TEXT PRIMARY KEY,
                    last_active_file_id TEXT,
                    last_active_folder_id TEXT,
                    current_selection_id TEXT,
                    turn_index INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def add(self, conversation_id: str, entity: Entity) -> None:
        """Add an entity to the store."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO entities (id, conversation_id, data, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (entity.id, conversation_id, json.dumps(entity.to_dict()))
            )
            conn.commit()

    def get(self, entity_id: str) -> Optional[Entity]:
        """Get an entity by ID."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT data FROM entities WHERE id = ?",
                (entity_id,)
            ).fetchone()
            if row:
                return Entity.from_dict(json.loads(row[0]))
        return None

    def get_by_path(self, conversation_id: str, path: str) -> Optional[Entity]:
        """Get an entity by its path within a conversation."""
        abs_path = os.path.realpath(os.path.expanduser(path))
        entities = self.get_all(conversation_id)
        for entity in entities:
            if entity.absolute_path == abs_path:
                return entity
        return None

    def get_all(self, conversation_id: str) -> list[Entity]:
        """Get all entities for a conversation."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT data FROM entities WHERE conversation_id = ? ORDER BY created_at DESC",
                (conversation_id,)
            ).fetchall()
            return [Entity.from_dict(json.loads(row[0])) for row in rows]

    def get_recent(
        self,
        conversation_id: str,
        kind: Optional[EntityKind] = None,
        limit: int = 10,
    ) -> list[Entity]:
        """Get recent entities, optionally filtered by kind."""
        entities = self.get_all(conversation_id)
        if kind:
            entities = [e for e in entities if e.kind == kind]
        return entities[:limit]

    def update(self, entity: Entity) -> None:
        """Update an existing entity."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE entities SET data = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (json.dumps(entity.to_dict()), entity.id)
            )
            conn.commit()

    def remove(self, entity_id: str) -> None:
        """Remove an entity from the store."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
            conn.commit()

    def clear_conversation(self, conversation_id: str) -> None:
        """Clear all entities for a conversation."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM entities WHERE conversation_id = ?",
                (conversation_id,)
            )
            conn.execute(
                "DELETE FROM conversation_state WHERE conversation_id = ?",
                (conversation_id,)
            )
            conn.commit()

    # --- Conversation State ---

    def get_turn_index(self, conversation_id: str) -> int:
        """Get current turn index for a conversation."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT turn_index FROM conversation_state WHERE conversation_id = ?",
                (conversation_id,)
            ).fetchone()
            return row[0] if row else 0

    def increment_turn(self, conversation_id: str) -> int:
        """Increment and return the turn index."""
        with sqlite3.connect(self.db_path) as conn:
            current = self.get_turn_index(conversation_id)
            new_index = current + 1
            conn.execute(
                """
                INSERT INTO conversation_state (conversation_id, turn_index, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    turn_index = ?,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (conversation_id, new_index, new_index)
            )
            conn.commit()
            return new_index

    def set_last_active_file(self, conversation_id: str, entity_id: Optional[str]) -> None:
        """Set the last active file entity."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO conversation_state (conversation_id, last_active_file_id, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    last_active_file_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (conversation_id, entity_id, entity_id)
            )
            conn.commit()

    def get_last_active_file(self, conversation_id: str) -> Optional[Entity]:
        """Get the last active file entity."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT last_active_file_id FROM conversation_state WHERE conversation_id = ?",
                (conversation_id,)
            ).fetchone()
            if row and row[0]:
                return self.get(row[0])
        return None

    def set_last_active_folder(self, conversation_id: str, entity_id: Optional[str]) -> None:
        """Set the last active folder entity."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO conversation_state (conversation_id, last_active_folder_id, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    last_active_folder_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (conversation_id, entity_id, entity_id)
            )
            conn.commit()

    def get_last_active_folder(self, conversation_id: str) -> Optional[Entity]:
        """Get the last active folder entity."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT last_active_folder_id FROM conversation_state WHERE conversation_id = ?",
                (conversation_id,)
            ).fetchone()
            if row and row[0]:
                return self.get(row[0])
        return None

    def set_current_selection(self, conversation_id: str, entity_id: Optional[str]) -> None:
        """Set the current selection entity."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO conversation_state (conversation_id, current_selection_id, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    current_selection_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (conversation_id, entity_id, entity_id)
            )
            conn.commit()

    def get_current_selection(self, conversation_id: str) -> Optional[Entity]:
        """Get the current selection entity."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT current_selection_id FROM conversation_state WHERE conversation_id = ?",
                (conversation_id,)
            ).fetchone()
            if row and row[0]:
                return self.get(row[0])
        return None

    def get_selection_items(self, conversation_id: str, selection_id: str) -> list[Entity]:
        """Get all entities in a selection."""
        selection = self.get(selection_id)
        if not selection or selection.kind != EntityKind.SELECTION:
            return []
        return [e for eid in selection.selection_ids if (e := self.get(eid))]
