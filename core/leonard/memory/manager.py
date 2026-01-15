"""
Memory Manager - Coordinates all memory components.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from leonard.memory.indexer import Indexer, IndexResult, IndexingStatus
from leonard.memory.retriever import Retriever
from leonard.memory.settings import MemorySettings, IndexPath
from leonard.memory.vault import Vault, SourceInfo
from leonard.utils.logging import logger


@dataclass
class MemoryStatus:
    """Overall memory system status."""

    initialized: bool
    rag_enabled: bool
    total_chunks: int
    total_sources: int
    indexing_status: IndexingStatus
    index_paths: list[dict]


class MemoryManager:
    """
    Coordinates all memory components.

    Provides a unified interface for:
    - Indexing documents
    - Retrieving relevant context
    - Managing index paths
    - Configuring RAG settings
    """

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Initialize the memory manager.

        Args:
            data_dir: Base directory for all memory data (default: ~/.leonard)
        """
        self.data_dir = data_dir or Path.home() / ".leonard"

        # Components
        self.settings = MemorySettings(self.data_dir)
        self.vault = Vault(self.data_dir / "vault")
        self.indexer = Indexer(self.vault)
        self.retriever = Retriever(self.vault)

        self._initialized = False

        logger.info("MemoryManager created")

    async def initialize(self) -> None:
        """
        Initialize all memory components.

        This downloads the embedding model if needed and
        connects to the vector database.
        """
        if self._initialized:
            return

        logger.info("Initializing memory system...")

        # Initialize vault (which initializes embeddings)
        await self.vault.initialize()

        # Start background indexing if auto_index is enabled
        if self.settings.config.auto_index:
            await self.indexer.start_background_indexing()

            # Queue all enabled paths for indexing
            for ip in self.settings.get_enabled_paths():
                if ip.enabled:
                    await self.indexer.queue_directory(
                        Path(ip.path),
                        recursive=ip.recursive,
                    )

        self._initialized = True
        logger.info("Memory system initialized")

    async def shutdown(self) -> None:
        """Shutdown the memory system."""
        await self.indexer.stop_background_indexing()
        logger.info("Memory system shut down")

    # ─────────────────────────────────────────────────────────
    # RAG CONTEXT RETRIEVAL
    # ─────────────────────────────────────────────────────────

    async def get_context_for_query(self, query: str) -> Optional[str]:
        """
        Main entry point for RAG - get relevant context for a query.

        This is the method the orchestrator should call.

        Args:
            query: User's message/query

        Returns:
            Formatted context string or None if RAG is disabled or no matches
        """
        if not self._initialized:
            await self.initialize()

        if not self.settings.config.rag_enabled:
            return None

        return await self.retriever.get_context_for_query(
            query,
            top_k=self.settings.config.top_k,
            min_score=self.settings.config.min_score,
            max_chars=self.settings.config.max_context_chars,
        )

    # ─────────────────────────────────────────────────────────
    # INDEX PATH MANAGEMENT
    # ─────────────────────────────────────────────────────────

    async def add_index_path(
        self,
        path: str,
        recursive: bool = True,
        index_now: bool = True,
    ) -> IndexPath:
        """
        Add a path to be indexed.

        Args:
            path: Path to index
            recursive: Whether to index subdirectories
            index_now: Whether to start indexing immediately

        Returns:
            The created IndexPath
        """
        if not self._initialized:
            await self.initialize()

        # Add to settings
        index_path = self.settings.add_path(path, recursive=recursive)

        # Start indexing if requested
        if index_now:
            await self.indexer.queue_directory(
                Path(path).expanduser(),
                recursive=recursive,
            )

        return index_path

    async def remove_index_path(self, path: str) -> bool:
        """
        Remove a path from indexing and delete its indexed content.

        Args:
            path: Path to remove

        Returns:
            True if removed, False if not found
        """
        if not self._initialized:
            await self.initialize()

        # Get resolved path
        resolved_path = str(Path(path).expanduser().resolve())

        # Remove from vault (all chunks from files in this path)
        sources = await self.vault.list_sources()
        for source in sources:
            if source.source_path.startswith(resolved_path):
                await self.vault.delete_by_source(source.source_path)

        # Remove from settings
        return self.settings.remove_path(path)

    async def get_index_paths(self) -> list[IndexPath]:
        """Get all configured index paths."""
        return self.settings.index_paths

    # ─────────────────────────────────────────────────────────
    # DIRECT INDEXING
    # ─────────────────────────────────────────────────────────

    async def index_file(self, file_path: str) -> IndexResult:
        """
        Index a single file.

        Args:
            file_path: Path to the file

        Returns:
            IndexResult with status
        """
        if not self._initialized:
            await self.initialize()

        return await self.indexer.index_file(Path(file_path))

    async def index_directory(
        self,
        directory: str,
        recursive: bool = True,
    ) -> list[IndexResult]:
        """
        Index all files in a directory.

        Args:
            directory: Path to the directory
            recursive: Whether to include subdirectories

        Returns:
            List of IndexResult for each file
        """
        if not self._initialized:
            await self.initialize()

        results = await self.indexer.index_directory(
            Path(directory),
            recursive=recursive,
        )

        # Update settings with stats
        total_chunks = sum(r.chunks_indexed for r in results if r.success)
        self.settings.update_path_stats(
            directory,
            chunk_count=total_chunks,
            last_indexed=datetime.now(),
        )

        return results

    async def index_text(self, text: str, source: str) -> IndexResult:
        """
        Index raw text content.

        Args:
            text: Text to index
            source: Source identifier

        Returns:
            IndexResult with status
        """
        if not self._initialized:
            await self.initialize()

        return await self.indexer.index_text(text, source)

    # ─────────────────────────────────────────────────────────
    # CONFIGURATION
    # ─────────────────────────────────────────────────────────

    def set_rag_enabled(self, enabled: bool) -> None:
        """Enable or disable RAG."""
        self.settings.config.rag_enabled = enabled
        self.settings.save()
        logger.info(f"RAG {'enabled' if enabled else 'disabled'}")

    def is_rag_enabled(self) -> bool:
        """Check if RAG is enabled."""
        return self.settings.config.rag_enabled

    def get_config(self) -> dict:
        """Get current configuration."""
        from dataclasses import asdict
        return asdict(self.settings.config)

    def update_config(
        self,
        rag_enabled: Optional[bool] = None,
        auto_index: Optional[bool] = None,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
        max_context_chars: Optional[int] = None,
    ) -> None:
        """
        Update configuration.

        Args:
            rag_enabled: Enable/disable RAG
            auto_index: Enable/disable auto-indexing
            top_k: Number of chunks to retrieve
            min_score: Minimum relevance score
            max_context_chars: Maximum context length
        """
        if rag_enabled is not None:
            self.settings.config.rag_enabled = rag_enabled
        if auto_index is not None:
            self.settings.config.auto_index = auto_index
        if top_k is not None:
            self.settings.config.top_k = top_k
        if min_score is not None:
            self.settings.config.min_score = min_score
        if max_context_chars is not None:
            self.settings.config.max_context_chars = max_context_chars

        self.settings.save()

    # ─────────────────────────────────────────────────────────
    # STATUS AND INFO
    # ─────────────────────────────────────────────────────────

    async def get_status(self) -> MemoryStatus:
        """Get overall memory system status."""
        chunk_count = await self.vault.get_chunk_count() if self._initialized else 0
        sources = await self.vault.list_sources() if self._initialized else []

        return MemoryStatus(
            initialized=self._initialized,
            rag_enabled=self.settings.config.rag_enabled,
            total_chunks=chunk_count,
            total_sources=len(sources),
            indexing_status=self.indexer.get_status(),
            index_paths=[ip.to_dict() for ip in self.settings.index_paths],
        )

    async def list_sources(self) -> list[SourceInfo]:
        """List all indexed sources."""
        if not self._initialized:
            await self.initialize()

        return await self.vault.list_sources()

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        """
        Manual semantic search (for debugging/UI).

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of search results
        """
        if not self._initialized:
            await self.initialize()

        results = await self.vault.search(query, limit=limit)
        return [
            {
                "content": r.content[:200] + "..." if len(r.content) > 200 else r.content,
                "source": r.source,
                "score": r.score,
            }
            for r in results
        ]

    async def clear_all(self) -> None:
        """Clear all indexed data."""
        if not self._initialized:
            await self.initialize()

        await self.vault.clear()
        logger.info("Cleared all indexed data")

    @property
    def is_initialized(self) -> bool:
        """Check if the memory system is initialized."""
        return self._initialized
