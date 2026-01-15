"""
Download GGUF models from HuggingFace.
User can search and download any GGUF model.
"""

import asyncio
import shutil
from pathlib import Path
from typing import Callable, Optional

from huggingface_hub import HfApi, hf_hub_download
from pydantic import BaseModel

from leonard.utils.logging import logger


class GGUFFile(BaseModel):
    """Represents a GGUF file in a HuggingFace repository."""

    filename: str
    size: int = 0  # bytes
    quantization: str  # Q4_K_M, Q5_K_S, etc.


class HFModel(BaseModel):
    """Represents a model from HuggingFace."""

    repo_id: str  # e.g., "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
    name: str
    author: str
    downloads: int
    likes: int
    gguf_files: list[GGUFFile]
    tags: list[str] = []
    description: str = ""


class ModelDownloader:
    """
    Search and download GGUF models from HuggingFace.
    """

    # Known quantization levels in order of quality/size
    QUANTIZATIONS = [
        "Q2_K",
        "Q3_K_S",
        "Q3_K_M",
        "Q3_K_L",
        "Q4_0",
        "Q4_K_S",
        "Q4_K_M",
        "Q5_0",
        "Q5_K_S",
        "Q5_K_M",
        "Q6_K",
        "Q8_0",
        "F16",
        "F32",
    ]

    # Incompatible architectures (not supported by llama.cpp)
    INCOMPATIBLE_PATTERNS = [
        "falcon-h1",  # Falcon Hybrid (H1, H1R)
        "mamba",      # Mamba / Mamba2 (State Space)
        "rwkv",       # RWKV (RNN-based)
        "jamba",      # Jamba (Mamba + Transformer hybrid)
        "griffin",    # Griffin architecture
        "recurrentgemma",  # Recurrent Gemma
        "-ssm",       # State Space Models
        "image",      # Vision/Image models
        "vision",     # Vision models
        "vl-",        # Vision-Language
        "-vl",        # Vision-Language
        "llava",      # LLaVA multimodal
        "minicpm-v",  # MiniCPM Vision
        "qwen-vl",    # Qwen Vision-Language
        "cogvlm",     # CogVLM
        "internvl",   # InternVL
    ]

    def __init__(self, models_dir: Path | None = None):
        self.models_dir = models_dir or Path.home() / ".leonard" / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.api = HfApi()

    def is_compatible(self, repo_id: str, tags: list[str] | None = None) -> bool:
        """
        Check if a model is compatible with llama.cpp.

        Args:
            repo_id: HuggingFace repository ID
            tags: Optional list of model tags

        Returns:
            True if compatible, False otherwise
        """
        repo_lower = repo_id.lower()

        # Check repo name against incompatible patterns
        for pattern in self.INCOMPATIBLE_PATTERNS:
            if pattern in repo_lower:
                return False

        # Check tags if provided
        if tags:
            tags_lower = [t.lower() for t in tags]
            incompatible_tags = ["mamba", "rwkv", "vision", "image-to-text", "image-text-to-text"]
            for tag in incompatible_tags:
                if tag in tags_lower:
                    return False

        return True

    async def search(self, query: str, limit: int = 20) -> list[HFModel]:
        """
        Search for GGUF models on HuggingFace.

        Args:
            query: Search term (e.g., "qwen", "codellama", "llama 3.2")
            limit: Maximum number of results

        Returns:
            List of HFModel with their available GGUF files
        """
        loop = asyncio.get_event_loop()

        # Search in thread pool (HfApi is sync)
        models = await loop.run_in_executor(
            None,
            lambda: list(
                self.api.list_models(
                    search=query,
                    filter="gguf",
                    sort="downloads",
                    direction=-1,
                    limit=limit,
                )
            ),
        )

        results = []
        for model in models:
            try:
                # Extract tags from model info
                tags = list(model.tags) if model.tags else []

                # Skip incompatible models
                if not self.is_compatible(model.id, tags):
                    logger.debug(f"Skipping incompatible model: {model.id}")
                    continue

                # Get files in repository
                files = await loop.run_in_executor(
                    None, lambda m=model: self.api.list_repo_files(m.id)
                )

                gguf_files = self._parse_gguf_files(files)

                if gguf_files:
                    results.append(
                        HFModel(
                            repo_id=model.id,
                            name=model.id.split("/")[-1],
                            author=model.id.split("/")[0],
                            downloads=model.downloads or 0,
                            likes=model.likes or 0,
                            gguf_files=gguf_files,
                            tags=tags,
                        )
                    )
            except Exception as e:
                logger.warning(f"Failed to get files for {model.id}: {e}")
                continue

        return results

    async def get_model_info(self, repo_id: str) -> Optional[HFModel]:
        """
        Get detailed info for a specific model, including tags and description.

        Args:
            repo_id: HuggingFace repository ID

        Returns:
            HFModel with metadata, or None if not found
        """
        loop = asyncio.get_event_loop()

        try:
            # Get model info
            model_info = await loop.run_in_executor(
                None, lambda: self.api.model_info(repo_id)
            )

            # Get files
            files = await loop.run_in_executor(
                None, lambda: self.api.list_repo_files(repo_id)
            )

            gguf_files = self._parse_gguf_files(files)

            # Get description from model card
            description = ""
            if model_info.card_data and hasattr(model_info.card_data, "description"):
                description = model_info.card_data.description or ""

            # Extract tags
            tags = list(model_info.tags) if model_info.tags else []

            return HFModel(
                repo_id=repo_id,
                name=repo_id.split("/")[-1],
                author=repo_id.split("/")[0],
                downloads=model_info.downloads or 0,
                likes=model_info.likes or 0,
                gguf_files=gguf_files,
                tags=tags,
                description=description,
            )

        except Exception as e:
            logger.warning(f"Failed to get model info for {repo_id}: {e}")
            return None

    def _parse_gguf_files(self, files: list[str]) -> list[GGUFFile]:
        """Parse GGUF filenames to extract quantization info."""
        gguf_files = [f for f in files if f.endswith(".gguf")]

        parsed = []
        for f in gguf_files:
            quant = self._extract_quantization(f)
            parsed.append(
                GGUFFile(
                    filename=f,
                    size=0,  # Will be filled on download
                    quantization=quant,
                )
            )

        return sorted(parsed, key=lambda x: x.quantization)

    def _extract_quantization(self, filename: str) -> str:
        """Extract quantization level from filename."""
        name_upper = filename.upper()
        for q in self.QUANTIZATIONS:
            if q in name_upper:
                return q
        return "unknown"

    async def download(
        self,
        repo_id: str,
        filename: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> Path:
        """
        Download a specific GGUF file from HuggingFace.

        Args:
            repo_id: HuggingFace repository ID (e.g., "Qwen/Qwen2.5-1.5B-Instruct-GGUF")
            filename: Name of the GGUF file to download
            progress_callback: Optional callback (downloaded_bytes, total_bytes)
            cancel_event: Optional event to cancel the download

        Returns:
            Path to the downloaded file
        """
        # Create model directory
        safe_repo_name = repo_id.replace("/", "_")
        model_dir = self.models_dir / safe_repo_name
        model_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Downloading {repo_id}/{filename}...")

        loop = asyncio.get_event_loop()

        def do_download():
            import httpx
            from huggingface_hub import hf_hub_url

            # Get download URL
            url = hf_hub_url(repo_id, filename)

            # Destination path
            dest_path = model_dir / filename

            # Use httpx with streaming and follow redirects
            with httpx.Client(follow_redirects=True, timeout=None) as client:
                with client.stream("GET", url) as response:
                    response.raise_for_status()

                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0

                    # Report initial progress
                    if progress_callback:
                        progress_callback(0, total_size)

                    # Download in chunks
                    with open(dest_path, 'wb') as f:
                        for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                            # Check for cancellation
                            if cancel_event and cancel_event.is_set():
                                raise InterruptedError("Download cancelled")

                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)

                                if progress_callback:
                                    progress_callback(downloaded, total_size)

            return str(dest_path)

        try:
            local_path = await loop.run_in_executor(None, do_download)
            logger.info(f"Downloaded to {local_path}")
            return Path(local_path)
        except InterruptedError:
            logger.info(f"Download cancelled: {repo_id}/{filename}")
            raise
        except Exception as e:
            logger.error(f"Download failed: {e}")
            # Clean up partial download
            partial_path = model_dir / filename
            if partial_path.exists():
                partial_path.unlink()
            raise

    def list_downloaded(self) -> list[dict]:
        """List all downloaded GGUF models."""
        models = []

        for model_dir in self.models_dir.iterdir():
            if model_dir.is_dir():
                for gguf_file in model_dir.rglob("*.gguf"):
                    models.append(
                        {
                            "repo_id": model_dir.name.replace("_", "/", 1),
                            "filename": gguf_file.name,
                            "path": str(gguf_file),
                            "size_bytes": gguf_file.stat().st_size,
                            "size_formatted": self._format_size(gguf_file.stat().st_size),
                        }
                    )

        return models

    def get_model_path(self, repo_id: str, filename: str) -> Optional[Path]:
        """
        Get path to a downloaded model, or None if not downloaded.

        Args:
            repo_id: HuggingFace repository ID
            filename: Name of the GGUF file

        Returns:
            Path to the file if it exists, None otherwise
        """
        safe_repo_name = repo_id.replace("/", "_")
        model_path = self.models_dir / safe_repo_name / filename

        if model_path.exists():
            return model_path

        # Also check in subdirectories (some repos have nested structure)
        for path in (self.models_dir / safe_repo_name).rglob(filename):
            if path.exists():
                return path

        return None

    def delete(self, repo_id: str, filename: str | None = None) -> bool:
        """
        Delete a downloaded model.

        Args:
            repo_id: HuggingFace repository ID
            filename: Specific file to delete, or None to delete entire model

        Returns:
            True if deleted, False if not found
        """
        safe_repo_name = repo_id.replace("/", "_")
        model_dir = self.models_dir / safe_repo_name

        if filename:
            file_path = model_dir / filename
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted {file_path}")
                # Remove dir if empty
                if model_dir.exists() and not any(model_dir.iterdir()):
                    model_dir.rmdir()
                return True
        else:
            if model_dir.exists():
                shutil.rmtree(model_dir)
                logger.info(f"Deleted {model_dir}")
                return True

        return False

    def _format_size(self, bytes_size: int) -> str:
        """Format bytes as human-readable string."""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes_size < 1024:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024
        return f"{bytes_size:.1f} TB"
