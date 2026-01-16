"""Memory API routes - Simplified for LlamaIndex."""

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


class MemoryStatusResponse(BaseModel):
    """Memory system status."""
    enabled: bool
    indexed: bool
    indexing: bool
    indexed_count: int = 0
    indexed_files: list[str] = []


class ToggleRequest(BaseModel):
    """Request to toggle memory."""
    enabled: bool


# ─────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────


@router.get("/status", response_model=MemoryStatusResponse)
async def get_status():
    """Get memory system status."""
    try:
        mm = await get_memory_manager()
        status = mm.get_status()
        return MemoryStatusResponse(**status)
    except Exception as e:
        logger.error(f"Error getting memory status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/toggle", response_model=MemoryStatusResponse)
async def toggle_memory(request: ToggleRequest):
    """Enable or disable document memory."""
    try:
        mm = await get_memory_manager()
        await mm.toggle(request.enabled)
        status = mm.get_status()
        return MemoryStatusResponse(**status)
    except Exception as e:
        logger.error(f"Error toggling memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reindex", response_model=MemoryStatusResponse)
async def reindex():
    """Force rebuild the document index."""
    try:
        mm = await get_memory_manager()
        await mm.reindex()
        status = mm.get_status()
        return MemoryStatusResponse(**status)
    except Exception as e:
        logger.error(f"Error reindexing: {e}")
        raise HTTPException(status_code=500, detail=str(e))
