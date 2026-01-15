"""
Memory settings and index path persistence.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from leonard.utils.logging import logger


@dataclass
class IndexPath:
    """Configuration for an indexed path."""

    path: str
    recursive: bool = True
    patterns: Optional[list[str]] = None  # e.g., ["*.py", "*.md"]
    enabled: bool = True
    last_indexed: Optional[str] = None  # ISO format datetime
    chunk_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "IndexPath":
        return cls(**data)


@dataclass
class MemoryConfig:
    """Configuration for the memory system."""

    rag_enabled: bool = True
    auto_index: bool = True  # Auto-index on startup
    top_k: int = 5  # Default number of chunks to retrieve
    min_score: float = 0.3  # Minimum relevance score
    max_context_chars: int = 4000  # Maximum context length


class MemorySettings:
    """
    Persistent settings for memory/indexing.

    Stores:
    - Index paths (folders to index)
    - RAG configuration
    - Auto-indexing preferences
    """

    SETTINGS_FILE = "memory_settings.json"

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Initialize memory settings.

        Args:
            data_dir: Directory for settings file (default: ~/.leonard)
        """
        self.data_dir = data_dir or Path.home() / ".leonard"
        self._settings_path = self.data_dir / self.SETTINGS_FILE

        # Settings
        self.index_paths: list[IndexPath] = []
        self.config = MemoryConfig()

        # Load existing settings
        self._load()

    def add_path(
        self,
        path: str,
        recursive: bool = True,
        patterns: Optional[list[str]] = None,
    ) -> IndexPath:
        """
        Add a new path to be indexed.

        Args:
            path: Path to index
            recursive: Whether to index subdirectories
            patterns: Optional file patterns to match

        Returns:
            The created IndexPath
        """
        # Expand and resolve path
        resolved_path = str(Path(path).expanduser().resolve())

        # Check if already exists
        existing = self.get_path(resolved_path)
        if existing:
            # Update existing
            existing.recursive = recursive
            existing.patterns = patterns
            existing.enabled = True
            self.save()
            return existing

        # Create new
        index_path = IndexPath(
            path=resolved_path,
            recursive=recursive,
            patterns=patterns,
            enabled=True,
        )
        self.index_paths.append(index_path)
        self.save()

        logger.info(f"Added index path: {resolved_path}")
        return index_path

    def remove_path(self, path: str) -> bool:
        """
        Remove a path from indexing.

        Args:
            path: Path to remove

        Returns:
            True if removed, False if not found
        """
        resolved_path = str(Path(path).expanduser().resolve())

        for i, ip in enumerate(self.index_paths):
            if ip.path == resolved_path:
                self.index_paths.pop(i)
                self.save()
                logger.info(f"Removed index path: {resolved_path}")
                return True

        return False

    def get_path(self, path: str) -> Optional[IndexPath]:
        """Get an index path by path string."""
        resolved_path = str(Path(path).expanduser().resolve())
        for ip in self.index_paths:
            if ip.path == resolved_path:
                return ip
        return None

    def update_path_stats(
        self,
        path: str,
        chunk_count: int,
        last_indexed: Optional[datetime] = None,
    ) -> None:
        """
        Update statistics for an indexed path.

        Args:
            path: Path that was indexed
            chunk_count: Number of chunks indexed
            last_indexed: Time of indexing (default: now)
        """
        ip = self.get_path(path)
        if ip:
            ip.chunk_count = chunk_count
            ip.last_indexed = (last_indexed or datetime.now()).isoformat()
            self.save()

    def get_enabled_paths(self) -> list[IndexPath]:
        """Get all enabled index paths."""
        return [ip for ip in self.index_paths if ip.enabled]

    def toggle_path(self, path: str, enabled: bool) -> bool:
        """
        Enable or disable an index path.

        Args:
            path: Path to toggle
            enabled: New enabled state

        Returns:
            True if found and updated, False if not found
        """
        ip = self.get_path(path)
        if ip:
            ip.enabled = enabled
            self.save()
            return True
        return False

    def save(self) -> None:
        """Save settings to disk."""
        self.data_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "index_paths": [ip.to_dict() for ip in self.index_paths],
            "config": asdict(self.config),
            "version": 1,
        }

        with open(self._settings_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.debug(f"Saved memory settings to {self._settings_path}")

    def _load(self) -> None:
        """Load settings from disk."""
        if not self._settings_path.exists():
            logger.info("No existing memory settings found, using defaults")
            return

        try:
            with open(self._settings_path, "r") as f:
                data = json.load(f)

            # Load index paths
            self.index_paths = [
                IndexPath.from_dict(ip) for ip in data.get("index_paths", [])
            ]

            # Load config
            if "config" in data:
                config_data = data["config"]
                self.config = MemoryConfig(
                    rag_enabled=config_data.get("rag_enabled", True),
                    auto_index=config_data.get("auto_index", True),
                    top_k=config_data.get("top_k", 5),
                    min_score=config_data.get("min_score", 0.3),
                    max_context_chars=config_data.get("max_context_chars", 4000),
                )

            logger.info(
                f"Loaded memory settings: {len(self.index_paths)} index paths"
            )

        except Exception as e:
            logger.error(f"Failed to load memory settings: {e}")

    def to_dict(self) -> dict:
        """Convert settings to dictionary."""
        return {
            "index_paths": [ip.to_dict() for ip in self.index_paths],
            "config": asdict(self.config),
        }
