"""Models module - Model downloading, registry, and management."""

from leonard.models.capabilities import (
    CapabilityDetector,
    detect_capabilities,
    get_detector,
)
from leonard.models.downloader import ModelDownloader, GGUFFile, HFModel
from leonard.models.registry import (
    ModelRegistry,
    RegisteredModel,
    ModelCapability,
    ModelRole,
)

__all__ = [
    "CapabilityDetector",
    "detect_capabilities",
    "get_detector",
    "ModelDownloader",
    "GGUFFile",
    "HFModel",
    "ModelRegistry",
    "RegisteredModel",
    "ModelCapability",
    "ModelRole",
]
