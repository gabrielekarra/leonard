"""
Reference resolver for mapping user utterances to tracked entities.

Handles:
- Pronouns: it, that, this, the file, the folder
- Ordinals: first, second, third, the second one
- Partial names: "the report", "report pdf"
- Recent references: "the file you just created"
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from leonard.context.entities import Entity, EntityKind, EntityStore


class ResolutionConfidence(str, Enum):
    """Confidence level of reference resolution."""
    HIGH = "high"  # >0.9 - Safe to auto-resolve
    MEDIUM = "medium"  # 0.6-0.9 - Safe for non-destructive, ask for destructive
    LOW = "low"  # 0.3-0.6 - Should ask for confirmation
    AMBIGUOUS = "ambiguous"  # Multiple equally valid matches
    NONE = "none"  # No matches found


@dataclass
class ResolvedReference:
    """Result of resolving a user reference."""
    entity: Optional[Entity]
    confidence: ResolutionConfidence
    score: float  # 0.0 - 1.0
    reason: str  # Human-readable explanation
    alternatives: list[Entity]  # Other possible matches

    @property
    def is_confident(self) -> bool:
        """True if resolution is confident enough for auto-action."""
        return self.confidence in (ResolutionConfidence.HIGH, ResolutionConfidence.MEDIUM)

    @property
    def needs_confirmation(self) -> bool:
        """True if resolution needs user confirmation."""
        return self.confidence in (
            ResolutionConfidence.LOW,
            ResolutionConfidence.AMBIGUOUS,
        )

    @property
    def is_ambiguous(self) -> bool:
        """True if multiple equally valid matches exist."""
        return self.confidence == ResolutionConfidence.AMBIGUOUS

    def format_disambiguation(self) -> str:
        """Format a disambiguation question for the user."""
        if not self.alternatives:
            return "I couldn't find a matching file. Can you specify the path?"

        if len(self.alternatives) == 1:
            e = self.alternatives[0]
            return f"Did you mean {e.display_name} ({e.absolute_path})?"

        lines = ["Which file did you mean?"]
        for i, e in enumerate(self.alternatives[:5], 1):
            lines.append(f"  {i}. {e.display_name} ({e.absolute_path})")
        return "\n".join(lines)


class ReferenceResolver:
    """
    Resolves user references like "it", "that file", "the second one"
    to tracked entities.
    """

    # Pronoun patterns that refer to "a file"
    FILE_PRONOUNS = [
        r"\bit\b",
        r"\bthat\b",
        r"\bthis\b",
        r"\bthe file\b",
        r"\bquel file\b",  # Italian
        r"\bquesto\b",
        r"\bquello\b",
    ]

    # Pronoun patterns that refer to "a folder"
    FOLDER_PRONOUNS = [
        r"\bthe folder\b",
        r"\bthe directory\b",
        r"\bthat folder\b",
        r"\bla cartella\b",  # Italian
        r"\bla directory\b",
    ]

    # Ordinal patterns
    ORDINALS = {
        r"\b(the )?(first|1st|primo)\b": 0,
        r"\b(the )?(second|2nd|secondo)\b": 1,
        r"\b(the )?(third|3rd|terzo)\b": 2,
        r"\b(the )?(fourth|4th|quarto)\b": 3,
        r"\b(the )?(fifth|5th|quinto)\b": 4,
        r"\b(the )?(last|ultimo)\b": -1,
    }

    # Recent action patterns
    RECENT_PATTERNS = [
        r"\b(the one|that one)\s*(we|you|I)?\s*(just|recently)?\s*(created|made|opened|read|viewed|listed)\b",
        r"\b(just|recently)\s*(created|made|opened|read|viewed)\b",
        r"\b(new|nuovo)\s*(file|folder|cartella)\b",
    ]

    def __init__(self, store: EntityStore):
        self.store = store

    def resolve(
        self,
        conversation_id: str,
        utterance: str,
        preferred_kind: Optional[EntityKind] = None,
        is_destructive: bool = False,
    ) -> ResolvedReference:
        """
        Resolve a user utterance to an entity.

        Args:
            conversation_id: The conversation context
            utterance: The user's message
            preferred_kind: If specified, prefer entities of this kind
            is_destructive: If True, require higher confidence

        Returns:
            ResolvedReference with the resolved entity and confidence
        """
        utterance_lower = utterance.lower().strip()

        # 1. Check for explicit path first
        explicit_path = self._extract_explicit_path(utterance)
        if explicit_path:
            entity = self.store.get_by_path(conversation_id, explicit_path)
            if entity:
                return ResolvedReference(
                    entity=entity,
                    confidence=ResolutionConfidence.HIGH,
                    score=1.0,
                    reason="Explicit path found in message",
                    alternatives=[],
                )
            # Path mentioned but not tracked - could still be valid
            return ResolvedReference(
                entity=None,
                confidence=ResolutionConfidence.HIGH,
                score=1.0,
                reason=f"Explicit path: {explicit_path}",
                alternatives=[],
            )

        # 2. Check for ordinal references (selection context)
        ordinal_match = self._resolve_ordinal(conversation_id, utterance_lower)
        if ordinal_match:
            return ordinal_match

        # 3. Check for pronouns referencing last active entity
        pronoun_match = self._resolve_pronoun(
            conversation_id, utterance_lower, preferred_kind
        )
        if pronoun_match.entity:
            # Downgrade confidence for destructive operations
            if is_destructive and pronoun_match.confidence == ResolutionConfidence.HIGH:
                pronoun_match = ResolvedReference(
                    entity=pronoun_match.entity,
                    confidence=ResolutionConfidence.MEDIUM,
                    score=pronoun_match.score * 0.9,
                    reason=pronoun_match.reason + " (destructive - verify)",
                    alternatives=pronoun_match.alternatives,
                )
            return pronoun_match

        # 4. Check for recent action patterns
        recent_match = self._resolve_recent(conversation_id, utterance_lower, preferred_kind)
        if recent_match.entity:
            return recent_match

        # 5. Try partial name matching
        name_match = self._resolve_by_name(conversation_id, utterance_lower, preferred_kind)
        if name_match.entity or name_match.alternatives:
            return name_match

        # 6. No match found
        return ResolvedReference(
            entity=None,
            confidence=ResolutionConfidence.NONE,
            score=0.0,
            reason="No matching entity found",
            alternatives=[],
        )

    def resolve_for_action(
        self,
        conversation_id: str,
        utterance: str,
        action: str,
    ) -> ResolvedReference:
        """
        Resolve reference with action-specific logic.

        For destructive actions (delete, move, overwrite), requires higher confidence.
        """
        is_destructive = action in ("delete", "move", "overwrite", "write")

        # Infer preferred kind from action
        preferred_kind = None
        if action in ("delete_file", "read_file", "write_file", "move_file", "copy_file"):
            preferred_kind = EntityKind.FILE
        elif action in ("list_directory", "create_directory"):
            preferred_kind = EntityKind.FOLDER

        return self.resolve(
            conversation_id=conversation_id,
            utterance=utterance,
            preferred_kind=preferred_kind,
            is_destructive=is_destructive,
        )

    def _extract_explicit_path(self, utterance: str) -> Optional[str]:
        """Extract an explicit file path from the utterance."""
        # Absolute path
        match = re.search(r'["\']?(/[^\s"\']+)["\']?', utterance)
        if match:
            return match.group(1)

        # Home path
        match = re.search(r'["\']?(~/[^\s"\']+)["\']?', utterance)
        if match:
            return match.group(1)

        return None

    def _resolve_ordinal(
        self,
        conversation_id: str,
        utterance: str,
    ) -> Optional[ResolvedReference]:
        """Resolve ordinal references like 'the second one'."""
        for pattern, index in self.ORDINALS.items():
            if re.search(pattern, utterance, re.IGNORECASE):
                selection = self.store.get_current_selection(conversation_id)
                if not selection:
                    return ResolvedReference(
                        entity=None,
                        confidence=ResolutionConfidence.LOW,
                        score=0.3,
                        reason="Ordinal used but no selection context",
                        alternatives=[],
                    )

                items = self.store.get_selection_items(conversation_id, selection.id)
                if not items:
                    return ResolvedReference(
                        entity=None,
                        confidence=ResolutionConfidence.LOW,
                        score=0.3,
                        reason="Selection exists but contains no items",
                        alternatives=[],
                    )

                # Handle negative index (last)
                if index < 0:
                    index = len(items) + index

                if 0 <= index < len(items):
                    return ResolvedReference(
                        entity=items[index],
                        confidence=ResolutionConfidence.HIGH,
                        score=0.95,
                        reason=f"Ordinal reference to item {index + 1} in selection",
                        alternatives=items,
                    )
                else:
                    return ResolvedReference(
                        entity=None,
                        confidence=ResolutionConfidence.LOW,
                        score=0.3,
                        reason=f"Ordinal {index + 1} out of range (only {len(items)} items)",
                        alternatives=items,
                    )
        return None

    def _resolve_pronoun(
        self,
        conversation_id: str,
        utterance: str,
        preferred_kind: Optional[EntityKind],
    ) -> ResolvedReference:
        """Resolve pronoun references like 'it', 'that file'."""
        # Check for file pronouns
        is_file_ref = any(
            re.search(p, utterance, re.IGNORECASE) for p in self.FILE_PRONOUNS
        )

        # Check for folder pronouns
        is_folder_ref = any(
            re.search(p, utterance, re.IGNORECASE) for p in self.FOLDER_PRONOUNS
        )

        # If both or neither, use preferred_kind
        if is_file_ref and not is_folder_ref:
            target_kind = EntityKind.FILE
        elif is_folder_ref and not is_file_ref:
            target_kind = EntityKind.FOLDER
        else:
            target_kind = preferred_kind

        # Get last active entity of the appropriate kind
        if target_kind == EntityKind.FOLDER:
            entity = self.store.get_last_active_folder(conversation_id)
            if entity:
                return ResolvedReference(
                    entity=entity,
                    confidence=ResolutionConfidence.HIGH,
                    score=0.9,
                    reason="Pronoun resolved to last active folder",
                    alternatives=[],
                )
        elif target_kind == EntityKind.FILE:
            entity = self.store.get_last_active_file(conversation_id)
            if entity:
                return ResolvedReference(
                    entity=entity,
                    confidence=ResolutionConfidence.HIGH,
                    score=0.9,
                    reason="Pronoun resolved to last active file",
                    alternatives=[],
                )

        # Try last active file, then folder
        entity = self.store.get_last_active_file(conversation_id)
        if entity:
            return ResolvedReference(
                entity=entity,
                confidence=ResolutionConfidence.MEDIUM,
                score=0.7,
                reason="Pronoun resolved to last active file (no explicit kind)",
                alternatives=[],
            )

        entity = self.store.get_last_active_folder(conversation_id)
        if entity:
            return ResolvedReference(
                entity=entity,
                confidence=ResolutionConfidence.MEDIUM,
                score=0.6,
                reason="Pronoun resolved to last active folder (no explicit kind)",
                alternatives=[],
            )

        # Fall back to current selection if present
        selection = self.store.get_current_selection(conversation_id)
        if selection:
            items = self.store.get_selection_items(conversation_id, selection.id)
            if len(items) == 1:
                return ResolvedReference(
                    entity=items[0],
                    confidence=ResolutionConfidence.MEDIUM,
                    score=0.6,
                    reason="Pronoun resolved to only item in selection",
                    alternatives=items,
                )
            if len(items) > 1:
                return ResolvedReference(
                    entity=None,
                    confidence=ResolutionConfidence.AMBIGUOUS,
                    score=0.4,
                    reason="Pronoun ambiguous within current selection",
                    alternatives=items,
                )

        return ResolvedReference(
            entity=None,
            confidence=ResolutionConfidence.NONE,
            score=0.0,
            reason="No active entity for pronoun resolution",
            alternatives=[],
        )

    def _resolve_recent(
        self,
        conversation_id: str,
        utterance: str,
        preferred_kind: Optional[EntityKind],
    ) -> ResolvedReference:
        """Resolve references to recently created/viewed entities."""
        for pattern in self.RECENT_PATTERNS:
            if re.search(pattern, utterance, re.IGNORECASE):
                recent = self.store.get_recent(conversation_id, kind=preferred_kind, limit=1)
                if recent:
                    return ResolvedReference(
                        entity=recent[0],
                        confidence=ResolutionConfidence.HIGH,
                        score=0.9,
                        reason="Resolved to most recent entity",
                        alternatives=recent,
                    )

        return ResolvedReference(
            entity=None,
            confidence=ResolutionConfidence.NONE,
            score=0.0,
            reason="No recent entity matches",
            alternatives=[],
        )

    def _resolve_by_name(
        self,
        conversation_id: str,
        utterance: str,
        preferred_kind: Optional[EntityKind],
    ) -> ResolvedReference:
        """Resolve by partial name matching."""
        # Extract potential file/folder names from utterance
        names = self._extract_names(utterance)
        if not names:
            return ResolvedReference(
                entity=None,
                confidence=ResolutionConfidence.NONE,
                score=0.0,
                reason="No identifiable name in utterance",
                alternatives=[],
            )

        all_entities = self.store.get_all(conversation_id)
        if preferred_kind:
            all_entities = [e for e in all_entities if e.kind == preferred_kind]

        matches = []
        for name in names:
            for entity in all_entities:
                if entity.matches_name(name):
                    matches.append((entity, self._name_match_score(name, entity)))

        if not matches:
            return ResolvedReference(
                entity=None,
                confidence=ResolutionConfidence.NONE,
                score=0.0,
                reason=f"No entity matches name(s): {names}",
                alternatives=[],
            )

        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)

        best_entity, best_score = matches[0]
        alternatives = [m[0] for m in matches]

        # Check for ambiguity (multiple high-scoring matches)
        if len(matches) > 1 and matches[1][1] > 0.7 and (best_score - matches[1][1]) < 0.1:
            return ResolvedReference(
                entity=None,
                confidence=ResolutionConfidence.AMBIGUOUS,
                score=best_score,
                reason="Multiple entities match equally well",
                alternatives=alternatives,
            )

        confidence = self._score_to_confidence(best_score)
        return ResolvedReference(
            entity=best_entity,
            confidence=confidence,
            score=best_score,
            reason=f"Name match with score {best_score:.2f}",
            alternatives=alternatives[1:] if len(alternatives) > 1 else [],
        )

    def _extract_names(self, utterance: str) -> list[str]:
        """Extract potential file/folder names from utterance."""
        names = []

        # Quoted names
        quoted = re.findall(r'["\']([^"\']+)["\']', utterance)
        names.extend(quoted)

        # File with extension
        files = re.findall(r'\b([\w\.-]+\.[a-zA-Z0-9]{1,6})\b', utterance)
        names.extend(files)

        # "the X" or "file X" or "folder X" patterns
        the_patterns = re.findall(
            r'(?:the|file|folder|il|la)\s+([a-zA-Z0-9_\-\.]+)',
            utterance,
            re.IGNORECASE
        )
        # Filter out common words
        stopwords = {'it', 'that', 'this', 'one', 'first', 'second', 'third', 'last',
                     'file', 'folder', 'directory', 'new', 'old', 'just', 'created'}
        names.extend([n for n in the_patterns if n.lower() not in stopwords])

        return list(set(names))

    def _name_match_score(self, query: str, entity: Entity) -> float:
        """Calculate match score between query and entity name."""
        query_lower = query.lower()
        name_lower = entity.display_name.lower()
        stem = name_lower.rsplit('.', 1)[0] if '.' in name_lower else name_lower

        # Exact match
        if query_lower == name_lower:
            return 1.0

        # Stem match
        if query_lower == stem:
            return 0.95

        # Query is prefix of name
        if name_lower.startswith(query_lower):
            return 0.85

        # Query in name
        if query_lower in name_lower:
            return 0.7

        # Fuzzy - query words in name
        query_words = set(query_lower.split())
        name_words = set(name_lower.replace('-', ' ').replace('_', ' ').split())
        overlap = len(query_words & name_words) / max(len(query_words), 1)
        if overlap > 0:
            return 0.5 + (overlap * 0.3)

        return 0.0

    def _score_to_confidence(self, score: float) -> ResolutionConfidence:
        """Convert numeric score to confidence level."""
        if score >= 0.9:
            return ResolutionConfidence.HIGH
        elif score >= 0.6:
            return ResolutionConfidence.MEDIUM
        elif score >= 0.3:
            return ResolutionConfidence.LOW
        else:
            return ResolutionConfidence.NONE

    def requires_confirmation(
        self,
        resolution: ResolvedReference,
        action: str,
    ) -> bool:
        """
        Determine if an action requires user confirmation.

        Destructive actions with medium or lower confidence need confirmation.
        """
        destructive_actions = {"delete", "delete_file", "delete_by_pattern", "overwrite", "move"}

        if action in destructive_actions:
            # Always confirm for destructive with less than high confidence
            if resolution.confidence != ResolutionConfidence.HIGH:
                return True
            # Even high confidence needs confirmation if it was pronoun resolution
            if "pronoun" in resolution.reason.lower():
                return True

        return resolution.needs_confirmation
