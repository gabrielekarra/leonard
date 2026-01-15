"""Memory module - Semantic storage and RAG."""

from leonard.memory.manager import MemoryManager, MemoryStatus
from leonard.memory.vault import Vault, SearchResult, SourceInfo
from leonard.memory.indexer import Indexer, IndexResult, IndexingStatus
from leonard.memory.retriever import Retriever, RetrievalResult
from leonard.memory.settings import MemorySettings, IndexPath, MemoryConfig
from leonard.memory.embeddings import EmbeddingModel
from leonard.memory.chunking import (
    DocumentChunk,
    TextChunker,
    CodeChunker,
    MarkdownChunker,
    get_chunker_for_file,
)

__all__ = [
    # Manager
    "MemoryManager",
    "MemoryStatus",
    # Vault
    "Vault",
    "SearchResult",
    "SourceInfo",
    # Indexer
    "Indexer",
    "IndexResult",
    "IndexingStatus",
    # Retriever
    "Retriever",
    "RetrievalResult",
    # Settings
    "MemorySettings",
    "IndexPath",
    "MemoryConfig",
    # Embeddings
    "EmbeddingModel",
    # Chunking
    "DocumentChunk",
    "TextChunker",
    "CodeChunker",
    "MarkdownChunker",
    "get_chunker_for_file",
]
