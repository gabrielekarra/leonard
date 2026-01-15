"""Models API routes."""

import asyncio
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from leonard.api.schemas import SuccessResponse
from leonard.models.capabilities import detect_capabilities
from leonard.models.downloader import ModelDownloader
from leonard.models.registry import ModelCapability, ModelRegistry
from leonard.utils.logging import logger

router = APIRouter(prefix="/models", tags=["models"])

# Global instances
downloader = ModelDownloader()
registry = ModelRegistry()


@dataclass
class DownloadTracker:
    """Track download progress and allow cancellation."""
    status: str = "pending"
    downloaded_bytes: int = 0
    total_bytes: int = 0
    progress_percent: float = 0.0
    path: Optional[str] = None
    error: Optional[str] = None
    model_id: Optional[str] = None
    capabilities: Optional[dict] = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)

    def update_progress(self, downloaded: int, total: int):
        self.downloaded_bytes = downloaded
        self.total_bytes = total
        if total > 0:
            self.progress_percent = round((downloaded / total) * 100, 1)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "progress_percent": self.progress_percent,
            "path": self.path,
            "error": self.error,
            "model_id": self.model_id,
            "capabilities": self.capabilities,
        }


# Track active downloads
active_downloads: dict[str, DownloadTracker] = {}


# ─────────────────────────────────────────────────────────
# REQUEST/RESPONSE MODELS
# ─────────────────────────────────────────────────────────


class SearchRequest(BaseModel):
    """Model search request."""

    query: str
    limit: int = 20


class DownloadRequest(BaseModel):
    """Model download request."""

    repo_id: str
    filename: str


class RegisterRequest(BaseModel):
    """Model registration request."""

    repo_id: str
    filename: str
    name: str
    capabilities: dict[str, float]  # {"coding": 0.9, "general": 0.7}
    context_length: int = 4096


class ModelResponse(BaseModel):
    """Model information response."""

    id: str
    name: str
    repo_id: str
    filename: str
    role: str
    capabilities: dict[str, float]
    context_length: int
    is_downloaded: bool
    local_path: str | None = None


# ─────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────


@router.get("/search")
async def search_models(q: str, limit: int = 20):
    """Search HuggingFace for GGUF models."""
    logger.info(f"Searching for models: {q}")
    results = await downloader.search(q, limit)
    return {"models": [r.model_dump() for r in results]}


@router.get("")
async def list_models():
    """List all registered models."""
    logger.info("Listing models")
    models = registry.list_all()
    return {
        "models": [
            ModelResponse(
                id=m.id,
                name=m.name,
                repo_id=m.repo_id,
                filename=m.filename,
                role=m.role.value,
                capabilities={k.value: v for k, v in m.capabilities.items()},
                context_length=m.context_length,
                is_downloaded=m.is_downloaded,
                local_path=m.local_path,
            ).model_dump()
            for m in models
        ]
    }


@router.get("/downloaded")
async def list_downloaded():
    """List downloaded model files."""
    return {"models": downloader.list_downloaded()}


@router.post("/download")
async def download_model(request: DownloadRequest, background_tasks: BackgroundTasks):
    """Start downloading a model."""
    download_id = f"{request.repo_id}:{request.filename}"

    if download_id in active_downloads:
        tracker = active_downloads[download_id]
        if tracker.status in ("downloading", "detecting_capabilities", "registering"):
            return {"status": "already_downloading", "download_id": download_id}

    # Create new tracker
    tracker = DownloadTracker(status="starting")
    active_downloads[download_id] = tracker

    background_tasks.add_task(
        _download_task,
        request.repo_id,
        request.filename,
        download_id,
    )

    return {"status": "started", "download_id": download_id}


@router.post("/download/{download_id:path}/cancel")
async def cancel_download(download_id: str):
    """Cancel an active download."""
    if download_id not in active_downloads:
        raise HTTPException(status_code=404, detail="Download not found")

    tracker = active_downloads[download_id]

    if tracker.status not in ("downloading", "starting"):
        return {"status": "cannot_cancel", "current_status": tracker.status}

    # Signal cancellation
    tracker.cancel_event.set()
    tracker.status = "cancelling"

    return {"status": "cancelling", "download_id": download_id}


async def _download_task(repo_id: str, filename: str, download_id: str):
    """Background download task with automatic capability detection."""
    tracker = active_downloads[download_id]

    try:
        tracker.status = "downloading"

        # Progress callback
        def on_progress(downloaded: int, total: int):
            tracker.update_progress(downloaded, total)

        # Download the model with progress tracking
        path = await downloader.download(
            repo_id,
            filename,
            progress_callback=on_progress,
            cancel_event=tracker.cancel_event,
        )

        # Get model metadata for capability detection
        tracker.status = "detecting_capabilities"
        tracker.progress_percent = 100.0
        model_info = await downloader.get_model_info(repo_id)

        tags = model_info.tags if model_info else []
        description = model_info.description if model_info else ""

        # Auto-detect capabilities
        capabilities = detect_capabilities(repo_id, tags, description)

        # Generate display name from repo
        name_parts = repo_id.split("/")[-1].replace("-GGUF", "").replace("-gguf", "")
        display_name = name_parts.replace("-", " ").replace("_", " ").title()

        # Auto-register the model
        tracker.status = "registering"
        model = registry.register(
            repo_id=repo_id,
            filename=filename,
            name=display_name,
            capabilities=capabilities,
            context_length=4096,
        )
        registry.update_download_status(model.id, True, str(path))

        # Mark as completed
        tracker.status = "completed"
        tracker.path = str(path)
        tracker.model_id = model.id
        tracker.capabilities = {k.value: v for k, v in capabilities.items()}

        logger.info(f"Model {model.id} downloaded and registered with auto-detected capabilities")

    except InterruptedError:
        tracker.status = "cancelled"
        tracker.error = "Download cancelled by user"
        logger.info(f"Download cancelled: {download_id}")

    except Exception as e:
        logger.error(f"Download failed: {e}")
        tracker.status = "error"
        tracker.error = str(e)


@router.get("/download/{download_id:path}/status")
async def download_status(download_id: str):
    """Check download status with progress info."""
    if download_id not in active_downloads:
        raise HTTPException(404, "Download not found")
    return active_downloads[download_id].to_dict()


@router.post("/register")
async def register_model(request: RegisterRequest):
    """Register a downloaded model with capabilities."""
    # Check if file exists
    path = downloader.get_model_path(request.repo_id, request.filename)
    if not path:
        raise HTTPException(400, "Model file not downloaded")

    # Convert capabilities
    caps = {ModelCapability(k): v for k, v in request.capabilities.items()}

    model = registry.register(
        repo_id=request.repo_id,
        filename=request.filename,
        name=request.name,
        capabilities=caps,
        context_length=request.context_length,
    )

    registry.update_download_status(model.id, True, str(path))

    return {
        "model": ModelResponse(
            id=model.id,
            name=model.name,
            repo_id=model.repo_id,
            filename=model.filename,
            role=model.role.value,
            capabilities={k.value: v for k, v in model.capabilities.items()},
            context_length=model.context_length,
            is_downloaded=model.is_downloaded,
            local_path=model.local_path,
        ).model_dump()
    }


@router.delete("/{model_id}")
async def delete_model(model_id: str):
    """Delete a model."""
    model = registry.get(model_id)
    if not model:
        raise HTTPException(404, "Model not found")

    # Delete file
    downloader.delete(model.repo_id, model.filename)

    # Remove from registry
    registry.delete(model_id)

    return {"status": "deleted"}


@router.get("/{model_id}")
async def get_model(model_id: str):
    """Get a specific model."""
    model = registry.get(model_id)
    if not model:
        raise HTTPException(404, "Model not found")

    return {
        "model": ModelResponse(
            id=model.id,
            name=model.name,
            repo_id=model.repo_id,
            filename=model.filename,
            role=model.role.value,
            capabilities={k.value: v for k, v in model.capabilities.items()},
            context_length=model.context_length,
            is_downloaded=model.is_downloaded,
            local_path=model.local_path,
        ).model_dump()
    }


# ─────────────────────────────────────────────────────────
# LEGACY ENDPOINTS (for compatibility with existing UI)
# ─────────────────────────────────────────────────────────


@router.post("/{model_id}/install")
async def install_model(model_id: str, background_tasks: BackgroundTasks):
    """
    Install a model by ID.
    This is a convenience endpoint that combines download + register.
    """
    model = registry.get(model_id)
    if not model:
        raise HTTPException(404, "Model not found in registry")

    if model.is_downloaded:
        return SuccessResponse(success=True, message="Model already installed")

    # Start download
    download_id = f"{model.repo_id}:{model.filename}"
    if download_id not in active_downloads:
        active_downloads[download_id] = {"status": "starting", "progress": 0}
        background_tasks.add_task(
            _install_task,
            model_id,
            model.repo_id,
            model.filename,
            download_id,
        )

    return SuccessResponse(
        success=True,
        message=f"Download started for {model.name}",
    )


async def _install_task(
    model_id: str, repo_id: str, filename: str, download_id: str
):
    """Background install task with automatic capability detection."""
    try:
        active_downloads[download_id]["status"] = "downloading"

        path = await downloader.download(repo_id, filename)

        # Get model from registry
        model = registry.get(model_id)

        # If model doesn't have capabilities yet, auto-detect them
        if model and not model.capabilities:
            active_downloads[download_id]["status"] = "detecting_capabilities"
            model_info = await downloader.get_model_info(repo_id)
            tags = model_info.tags if model_info else []
            description = model_info.description if model_info else ""
            capabilities = detect_capabilities(repo_id, tags, description)
            # Update model capabilities in registry
            model.capabilities = capabilities
            registry._save()

        # Update registry
        registry.update_download_status(model_id, True, str(path))

        active_downloads[download_id] = {
            "status": "completed",
            "path": str(path),
            "model_id": model_id,
        }
        logger.info(f"Model {model_id} installed successfully")

    except Exception as e:
        logger.error(f"Install failed: {e}")
        active_downloads[download_id] = {
            "status": "error",
            "error": str(e),
        }
