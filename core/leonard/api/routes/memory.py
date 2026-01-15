"""Memory API routes for RAG and indexing."""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from leonard.memory import MemoryManager
from leonard.utils.logging import logger

router = APIRouter(prefix="/memory", tags=["memory"])

# Global memory manager instance
_memory_manager: Optional[MemoryManager] = None


async def get_memory_manager() -> MemoryManager:
    """Get or create the memory manager instance."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
        await _memory_manager.initialize()
    return _memory_manager


# ─────────────────────────────────────────────────────────
# REQUEST/RESPONSE MODELS
# ─────────────────────────────────────────────────────────


class IndexPathRequest(BaseModel):
    """Request to add an index path."""

    path: str
    recursive: bool = True
    index_now: bool = True


class IndexPathResponse(BaseModel):
    """Response for index path operations."""

    path: str
    recursive: bool
    enabled: bool
    chunk_count: int
    last_indexed: Optional[str]


class MemoryStatusResponse(BaseModel):
    """Memory system status."""

    initialized: bool
    rag_enabled: bool
    total_chunks: int
    total_sources: int
    is_indexing: bool
    queue_size: int
    current_file: Optional[str]
    files_indexed: int
    files_failed: int


class SourceResponse(BaseModel):
    """Information about an indexed source."""

    source_path: str
    chunk_count: int
    indexed_at: str
    file_type: str


class MemoryConfigRequest(BaseModel):
    """Request to update memory configuration."""

    rag_enabled: Optional[bool] = None
    auto_index: Optional[bool] = None
    top_k: Optional[int] = None
    min_score: Optional[float] = None
    max_context_chars: Optional[int] = None


class MemoryConfigResponse(BaseModel):
    """Memory configuration."""

    rag_enabled: bool
    auto_index: bool
    top_k: int
    min_score: float
    max_context_chars: int


class SearchRequest(BaseModel):
    """Request for semantic search."""

    query: str
    limit: int = 10


class SearchResultResponse(BaseModel):
    """A single search result."""

    content: str
    source: str
    score: float


class IndexResultResponse(BaseModel):
    """Result of an indexing operation."""

    success: bool
    source: str
    chunks_indexed: int
    error: Optional[str]


# ─────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────


@router.get("/status", response_model=MemoryStatusResponse)
async def get_status():
    """Get memory system status."""
    try:
        mm = await get_memory_manager()
        status = await mm.get_status()

        return MemoryStatusResponse(
            initialized=status.initialized,
            rag_enabled=status.rag_enabled,
            total_chunks=status.total_chunks,
            total_sources=status.total_sources,
            is_indexing=status.indexing_status.is_indexing,
            queue_size=status.indexing_status.queue_size,
            current_file=status.indexing_status.current_file,
            files_indexed=status.indexing_status.files_indexed,
            files_failed=status.indexing_status.files_failed,
        )
    except Exception as e:
        logger.error(f"Error getting memory status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources", response_model=list[SourceResponse])
async def list_sources():
    """List all indexed sources."""
    try:
        mm = await get_memory_manager()
        sources = await mm.list_sources()

        return [
            SourceResponse(
                source_path=s.source_path,
                chunk_count=s.chunk_count,
                indexed_at=s.indexed_at.isoformat(),
                file_type=s.file_type,
            )
            for s in sources
        ]
    except Exception as e:
        logger.error(f"Error listing sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index", response_model=IndexPathResponse)
async def add_index_path(request: IndexPathRequest):
    """Add a path to be indexed."""
    try:
        mm = await get_memory_manager()
        index_path = await mm.add_index_path(
            request.path,
            recursive=request.recursive,
            index_now=request.index_now,
        )

        return IndexPathResponse(
            path=index_path.path,
            recursive=index_path.recursive,
            enabled=index_path.enabled,
            chunk_count=index_path.chunk_count,
            last_indexed=index_path.last_indexed,
        )
    except Exception as e:
        logger.error(f"Error adding index path: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/index/{path:path}")
async def remove_index_path(path: str):
    """Remove a path from the index."""
    try:
        mm = await get_memory_manager()
        # Decode path (it may be URL encoded)
        from urllib.parse import unquote
        decoded_path = unquote(path)

        success = await mm.remove_index_path(decoded_path)

        if success:
            return {"status": "ok", "message": f"Removed {decoded_path} from index"}
        else:
            raise HTTPException(status_code=404, detail="Path not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing index path: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/paths", response_model=list[IndexPathResponse])
async def get_index_paths():
    """Get all configured index paths."""
    try:
        mm = await get_memory_manager()
        paths = await mm.get_index_paths()

        return [
            IndexPathResponse(
                path=p.path,
                recursive=p.recursive,
                enabled=p.enabled,
                chunk_count=p.chunk_count,
                last_indexed=p.last_indexed,
            )
            for p in paths
        ]
    except Exception as e:
        logger.error(f"Error getting index paths: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config", response_model=MemoryConfigResponse)
async def get_config():
    """Get memory configuration."""
    try:
        mm = await get_memory_manager()
        config = mm.get_config()

        return MemoryConfigResponse(**config)
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config", response_model=MemoryConfigResponse)
async def update_config(request: MemoryConfigRequest):
    """Update memory configuration."""
    try:
        mm = await get_memory_manager()
        mm.update_config(
            rag_enabled=request.rag_enabled,
            auto_index=request.auto_index,
            top_k=request.top_k,
            min_score=request.min_score,
            max_context_chars=request.max_context_chars,
        )

        config = mm.get_config()
        return MemoryConfigResponse(**config)
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", response_model=list[SearchResultResponse])
async def search(request: SearchRequest):
    """Perform semantic search (for debugging/UI)."""
    try:
        mm = await get_memory_manager()
        results = await mm.search(request.query, limit=request.limit)

        return [SearchResultResponse(**r) for r in results]
    except Exception as e:
        logger.error(f"Error searching: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index/file", response_model=IndexResultResponse)
async def index_file(path: str):
    """Index a single file."""
    try:
        mm = await get_memory_manager()
        result = await mm.index_file(path)

        return IndexResultResponse(
            success=result.success,
            source=result.source,
            chunks_indexed=result.chunks_indexed,
            error=result.error,
        )
    except Exception as e:
        logger.error(f"Error indexing file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index/directory", response_model=list[IndexResultResponse])
async def index_directory(path: str, recursive: bool = True):
    """Index all files in a directory."""
    try:
        mm = await get_memory_manager()
        results = await mm.index_directory(path, recursive=recursive)

        return [
            IndexResultResponse(
                success=r.success,
                source=r.source,
                chunks_indexed=r.chunks_indexed,
                error=r.error,
            )
            for r in results
        ]
    except Exception as e:
        logger.error(f"Error indexing directory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear")
async def clear_all():
    """Clear all indexed data."""
    try:
        mm = await get_memory_manager()
        await mm.clear_all()
        return {"status": "ok", "message": "All indexed data cleared"}
    except Exception as e:
        logger.error(f"Error clearing data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/toggle")
async def toggle_rag(enabled: bool):
    """Enable or disable RAG."""
    try:
        mm = await get_memory_manager()
        mm.set_rag_enabled(enabled)
        return {
            "status": "ok",
            "rag_enabled": enabled,
            "message": f"RAG {'enabled' if enabled else 'disabled'}",
        }
    except Exception as e:
        logger.error(f"Error toggling RAG: {e}")
        raise HTTPException(status_code=500, detail=str(e))
