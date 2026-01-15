"""
Registry of available models with their capabilities.
Tracks which models are downloaded and their specializations.
"""

import json
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from leonard.utils.logging import logger


class ModelCapability(str, Enum):
    """Capabilities that models can have."""

    GENERAL = "general"
    CODING = "coding"
    REASONING = "reasoning"
    CREATIVE = "creative"
    MATH = "math"
    ANALYSIS = "analysis"


class ModelRole(str, Enum):
    """Role of the model in the orchestration system."""

    ROUTER = "router"  # The brain that decides which model to use
    WORKER = "worker"  # Models that do actual work
    SYNTHESIZER = "synth"  # Combines outputs (usually same as router)


class RegisteredModel(BaseModel):
    """A model registered in the system."""

    id: str  # Unique ID: "qwen2.5-1.5b-router"
    repo_id: str  # HF repo: "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
    filename: str  # GGUF file: "qwen2.5-1.5b-instruct-q4_k_m.gguf"
    name: str  # Display name: "Qwen 2.5 1.5B"
    role: ModelRole  # router, worker, or synth
    capabilities: dict[ModelCapability, float]  # Capability scores 0.0-1.0
    context_length: int = 4096
    is_downloaded: bool = False
    local_path: Optional[str] = None


class ModelRegistry:
    """
    Tracks all registered models and their capabilities.
    Persists to disk for state across restarts.
    """

    # Default router model - small, fast, always in memory
    ROUTER_MODEL = RegisteredModel(
        id="leonard-router",
        repo_id="Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        filename="qwen2.5-1.5b-instruct-q4_k_m.gguf",
        name="Leonard Router",
        role=ModelRole.ROUTER,
        capabilities={
            ModelCapability.GENERAL: 0.8,
            ModelCapability.REASONING: 0.85,
        },
        context_length=32768,
    )

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or Path.home() / ".leonard"
        self.registry_file = self.data_dir / "registry.json"
        self.models: dict[str, RegisteredModel] = {}

        self._load()
        self._ensure_router()

    def _ensure_router(self):
        """Ensure router model is always registered."""
        if self.ROUTER_MODEL.id not in self.models:
            self.models[self.ROUTER_MODEL.id] = self.ROUTER_MODEL
            self._save()

    def _load(self):
        """Load registry from disk."""
        if self.registry_file.exists():
            try:
                data = json.loads(self.registry_file.read_text())
                for model_data in data.get("models", []):
                    # Handle capability enum conversion
                    if "capabilities" in model_data:
                        model_data["capabilities"] = {
                            ModelCapability(k): v
                            for k, v in model_data["capabilities"].items()
                        }
                    model = RegisteredModel(**model_data)
                    self.models[model.id] = model
                logger.info(f"Loaded {len(self.models)} models from registry")
            except Exception as e:
                logger.error(f"Failed to load registry: {e}")
                self.models = {}

    def _save(self):
        """Save registry to disk."""
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Convert capabilities enum keys to strings for JSON
        models_data = []
        for m in self.models.values():
            model_dict = m.model_dump()
            model_dict["capabilities"] = {
                k.value if isinstance(k, ModelCapability) else k: v
                for k, v in model_dict["capabilities"].items()
            }
            models_data.append(model_dict)

        data = {"models": models_data}
        self.registry_file.write_text(json.dumps(data, indent=2, default=str))

    def register(
        self,
        repo_id: str,
        filename: str,
        name: str,
        capabilities: dict[ModelCapability, float],
        context_length: int = 4096,
    ) -> RegisteredModel:
        """
        Register a new worker model.

        Args:
            repo_id: HuggingFace repository ID
            filename: GGUF filename
            name: Display name for the model
            capabilities: Dict of capability -> score (0.0-1.0)
            context_length: Maximum context length

        Returns:
            The registered model
        """
        model_id = name.lower().replace(" ", "-").replace(".", "-")

        # Ensure unique ID
        base_id = model_id
        counter = 1
        while model_id in self.models:
            model_id = f"{base_id}-{counter}"
            counter += 1

        model = RegisteredModel(
            id=model_id,
            repo_id=repo_id,
            filename=filename,
            name=name,
            role=ModelRole.WORKER,
            capabilities=capabilities,
            context_length=context_length,
        )

        self.models[model_id] = model
        self._save()

        logger.info(f"Registered model: {model_id}")
        return model

    def update_download_status(
        self, model_id: str, is_downloaded: bool, local_path: str | None = None
    ):
        """Update model's download status."""
        if model_id in self.models:
            self.models[model_id].is_downloaded = is_downloaded
            self.models[model_id].local_path = local_path
            self._save()
            logger.info(f"Updated download status for {model_id}: {is_downloaded}")

    def get(self, model_id: str) -> Optional[RegisteredModel]:
        """Get model by ID."""
        return self.models.get(model_id)

    def get_router(self) -> RegisteredModel:
        """Get the router model."""
        return self.models.get(self.ROUTER_MODEL.id, self.ROUTER_MODEL)

    def get_available_workers(self) -> list[RegisteredModel]:
        """Get all downloaded worker models."""
        return [
            m
            for m in self.models.values()
            if m.role == ModelRole.WORKER and m.is_downloaded
        ]

    def get_best_for_capability(
        self, capability: ModelCapability
    ) -> Optional[RegisteredModel]:
        """
        Find best downloaded model for a capability.

        Args:
            capability: The capability to optimize for

        Returns:
            Best model for that capability, or None if no models available
        """
        available = self.get_available_workers()

        if not available:
            return None

        # Sort by capability score (descending)
        sorted_models = sorted(
            available,
            key=lambda m: m.capabilities.get(capability, 0),
            reverse=True,
        )

        return sorted_models[0] if sorted_models else None

    def list_all(self) -> list[RegisteredModel]:
        """List all registered models."""
        return list(self.models.values())

    def delete(self, model_id: str) -> bool:
        """
        Remove model from registry.

        Note: Cannot delete the router model.
        """
        if model_id in self.models and model_id != self.ROUTER_MODEL.id:
            del self.models[model_id]
            self._save()
            logger.info(f"Deleted model from registry: {model_id}")
            return True
        return False

    def unregister(self, model_id: str) -> bool:
        """Alias for delete."""
        return self.delete(model_id)
