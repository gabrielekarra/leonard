"""
Semantic vault for persistent memory storage using LanceDB.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from leonard.memory.chunking import DocumentChunk
from leonard.memory.embeddings import EmbeddingModel
from leonard.utils.logging import logger


@dataclass
class SearchResult:
    """A search result from the vault."""

    chunk_id: str
    content: str
    metadata: dict
    score: float
    source: str


@dataclass
class SourceInfo:
    """Information about an indexed source."""

    source_path: str
    chunk_count: int
    indexed_at: datetime
    file_type: str


class Vault:
    """
    Semantic storage vault using LanceDB.

    Stores document chunks with embeddings for efficient similarity search.
    Data is persisted to disk at ~/.leonard/vault/
    """

    TABLE_NAME = "documents"

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Initialize the vault.

        Args:
            data_dir: Directory for LanceDB storage (default: ~/.leonard/vault)
        """
        self.data_dir = data_dir or Path.home() / ".leonard" / "vault"
        self._db = None
        self._table = None
        self._embedding_model = EmbeddingModel()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize LanceDB and the embedding model."""
        if self._initialized:
            return

        # Ensure directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

        try:
            import lancedb

            # Initialize embedding model first
            await self._embedding_model.initialize()

            # Connect to LanceDB
            self._db = lancedb.connect(str(self.data_dir))

            # Check if table exists
            existing_tables = self._db.table_names()
            if self.TABLE_NAME in existing_tables:
                self._table = self._db.open_table(self.TABLE_NAME)
                logger.info(f"Opened existing vault table with {self._table.count_rows()} chunks")
            else:
                # Will be created on first store
                self._table = None
                logger.info("Vault table will be created on first store")

            self._initialized = True
            logger.info("Vault initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize vault: {e}")
            raise RuntimeError(f"Could not initialize vault: {e}")

    async def store(self, chunks: list[DocumentChunk]) -> list[str]:
        """
        Store document chunks with embeddings.

        Args:
            chunks: List of DocumentChunk objects to store

        Returns:
            List of chunk IDs
        """
        if not self._initialized:
            raise RuntimeError("Vault not initialized. Call initialize() first.")

        if not chunks:
            return []

        # Generate embeddings for all chunks
        texts = [chunk.content for chunk in chunks]
        embeddings = self._embedding_model.embed(texts)

        # Prepare data for LanceDB
        chunk_ids = []
        data = []

        for i, chunk in enumerate(chunks):
            chunk_id = str(uuid.uuid4())
            chunk_ids.append(chunk_id)

            data.append({
                "id": chunk_id,
                "content": chunk.content,
                "source": chunk.source,
                "chunk_index": chunk.chunk_index,
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
                "metadata": str(chunk.metadata),  # Serialize as string
                "indexed_at": datetime.now().isoformat(),
                "vector": embeddings[i].tolist(),
            })

        # Create or append to table
        import pyarrow as pa

        if self._table is None:
            self._table = self._db.create_table(self.TABLE_NAME, data=data)
            logger.info(f"Created vault table with {len(data)} chunks")
        else:
            self._table.add(data)
            logger.info(f"Added {len(data)} chunks to vault")

        return chunk_ids

    async def search(
        self,
        query: str,
        limit: int = 5,
        source_filter: Optional[str] = None,
    ) -> list[SearchResult]:
        """
        Vector similarity search.

        Args:
            query: Search query string
            limit: Maximum number of results
            source_filter: Optional filter by source path

        Returns:
            List of SearchResult objects sorted by relevance
        """
        if not self._initialized:
            raise RuntimeError("Vault not initialized. Call initialize() first.")

        if self._table is None:
            return []

        # Embed the query
        query_embedding = self._embedding_model.embed_query(query)

        # Build search query
        search_query = self._table.search(query_embedding.tolist())

        if source_filter:
            search_query = search_query.where(f"source = '{source_filter}'")

        # Execute search
        results = search_query.limit(limit).to_pandas()

        # Convert to SearchResult objects
        search_results = []
        for _, row in results.iterrows():
            search_results.append(
                SearchResult(
                    chunk_id=row["id"],
                    content=row["content"],
                    metadata=eval(row["metadata"]) if row["metadata"] else {},
                    score=1.0 - row["_distance"],  # Convert distance to similarity
                    source=row["source"],
                )
            )

        return search_results

    async def delete_by_source(self, source_path: str) -> int:
        """
        Delete all chunks from a specific source.

        Args:
            source_path: Path of the source to delete

        Returns:
            Number of chunks deleted
        """
        if not self._initialized:
            raise RuntimeError("Vault not initialized. Call initialize() first.")

        if self._table is None:
            return 0

        # Count chunks before deletion
        df = self._table.to_pandas()
        count_before = len(df[df["source"] == source_path])

        if count_before == 0:
            return 0

        # Delete by filtering
        self._table.delete(f"source = '{source_path}'")

        logger.info(f"Deleted {count_before} chunks from source: {source_path}")
        return count_before

    async def list_sources(self) -> list[SourceInfo]:
        """
        List all indexed sources with statistics.

        Returns:
            List of SourceInfo objects
        """
        if not self._initialized:
            raise RuntimeError("Vault not initialized. Call initialize() first.")

        if self._table is None:
            return []

        df = self._table.to_pandas()

        # Group by source
        sources = []
        for source_path in df["source"].unique():
            source_df = df[df["source"] == source_path]
            chunk_count = len(source_df)

            # Get earliest indexed_at for this source
            indexed_at = datetime.fromisoformat(source_df["indexed_at"].min())

            # Infer file type from source path
            file_ext = source_path.rsplit(".", 1)[-1] if "." in source_path else "unknown"

            sources.append(
                SourceInfo(
                    source_path=source_path,
                    chunk_count=chunk_count,
                    indexed_at=indexed_at,
                    file_type=file_ext,
                )
            )

        return sorted(sources, key=lambda x: x.indexed_at, reverse=True)

    async def get_chunk_count(self) -> int:
        """Get total number of chunks in the vault."""
        if self._table is None:
            return 0
        return self._table.count_rows()

    async def clear(self) -> None:
        """Clear all data from the vault."""
        if not self._initialized:
            raise RuntimeError("Vault not initialized. Call initialize() first.")

        if self._table is not None:
            self._db.drop_table(self.TABLE_NAME)
            self._table = None
            logger.info("Vault cleared")

    @property
    def is_initialized(self) -> bool:
        """Check if the vault is initialized."""
        return self._initialized
