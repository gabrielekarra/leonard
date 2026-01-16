"""
Conversation context and entity tracking for chat-aware file operations.

This module provides:
- Entity: Tracked file/folder references with metadata
- EntityStore: SQLite-backed persistent storage
- ReferenceResolver: Maps user utterances ("it", "that file") to entities
- ConversationContext: Per-conversation state management
"""

from leonard.context.entities import (
    Entity,
    EntityKind,
    EntityProvenance,
    EntityStore,
)
from leonard.context.resolver import (
    ReferenceResolver,
    ResolvedReference,
    ResolutionConfidence,
)
from leonard.context.conversation import ConversationContext

__all__ = [
    "Entity",
    "EntityKind",
    "EntityProvenance",
    "EntityStore",
    "ReferenceResolver",
    "ResolvedReference",
    "ResolutionConfidence",
    "ConversationContext",
]
