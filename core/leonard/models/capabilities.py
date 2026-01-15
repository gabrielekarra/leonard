"""
Automatic capability detection for models.
Infers what a model is good at from its metadata.
Zero configuration needed from the user.
"""

import re
from typing import Optional

from leonard.models.registry import ModelCapability
from leonard.utils.logging import logger


class CapabilityDetector:
    """
    Automatically detect model capabilities from:
    - Repository name
    - HuggingFace tags
    - Model card description
    - Known model patterns

    The user never configures anything. Leonard figures it out.
    """

    # Known patterns: model name keywords -> capability scores
    PATTERNS: dict[str, dict[ModelCapability, float]] = {
        # Coding models
        "code": {ModelCapability.CODING: 0.95, ModelCapability.REASONING: 0.7, ModelCapability.GENERAL: 0.6},
        "coder": {ModelCapability.CODING: 0.95, ModelCapability.REASONING: 0.7, ModelCapability.GENERAL: 0.6},
        "codellama": {ModelCapability.CODING: 0.95, ModelCapability.REASONING: 0.7, ModelCapability.GENERAL: 0.6},
        "wizardcoder": {ModelCapability.CODING: 0.95, ModelCapability.REASONING: 0.8, ModelCapability.GENERAL: 0.6},
        "starcoder": {ModelCapability.CODING: 0.9, ModelCapability.REASONING: 0.6, ModelCapability.GENERAL: 0.5},
        "deepseek-coder": {ModelCapability.CODING: 0.95, ModelCapability.REASONING: 0.75, ModelCapability.GENERAL: 0.6},
        "deepcoder": {ModelCapability.CODING: 0.9, ModelCapability.REASONING: 0.7, ModelCapability.GENERAL: 0.6},
        "codestral": {ModelCapability.CODING: 0.95, ModelCapability.REASONING: 0.75, ModelCapability.GENERAL: 0.6},
        "qwen2.5-coder": {ModelCapability.CODING: 0.95, ModelCapability.REASONING: 0.8, ModelCapability.GENERAL: 0.7},

        # Math models
        "math": {ModelCapability.MATH: 0.95, ModelCapability.REASONING: 0.85, ModelCapability.GENERAL: 0.5},
        "wizardmath": {ModelCapability.MATH: 0.95, ModelCapability.REASONING: 0.85, ModelCapability.GENERAL: 0.5},
        "metamath": {ModelCapability.MATH: 0.9, ModelCapability.REASONING: 0.8, ModelCapability.GENERAL: 0.5},
        "mathstral": {ModelCapability.MATH: 0.9, ModelCapability.REASONING: 0.85, ModelCapability.GENERAL: 0.6},
        "deepseek-math": {ModelCapability.MATH: 0.95, ModelCapability.REASONING: 0.85, ModelCapability.GENERAL: 0.5},

        # General/reasoning models
        "mistral": {ModelCapability.REASONING: 0.9, ModelCapability.GENERAL: 0.85, ModelCapability.CREATIVE: 0.75},
        "mixtral": {ModelCapability.REASONING: 0.9, ModelCapability.GENERAL: 0.85, ModelCapability.CODING: 0.7},
        "llama": {ModelCapability.GENERAL: 0.8, ModelCapability.REASONING: 0.75, ModelCapability.CREATIVE: 0.7},
        "llama-3": {ModelCapability.GENERAL: 0.85, ModelCapability.REASONING: 0.8, ModelCapability.CREATIVE: 0.75},
        "llama-3.1": {ModelCapability.GENERAL: 0.85, ModelCapability.REASONING: 0.85, ModelCapability.CODING: 0.7},
        "llama-3.2": {ModelCapability.GENERAL: 0.85, ModelCapability.REASONING: 0.8, ModelCapability.CREATIVE: 0.75},
        "qwen": {ModelCapability.REASONING: 0.85, ModelCapability.GENERAL: 0.85, ModelCapability.CODING: 0.7},
        "qwen2": {ModelCapability.REASONING: 0.9, ModelCapability.GENERAL: 0.85, ModelCapability.CODING: 0.75},
        "qwen2.5": {ModelCapability.REASONING: 0.9, ModelCapability.GENERAL: 0.9, ModelCapability.CODING: 0.8},
        "phi": {ModelCapability.REASONING: 0.8, ModelCapability.GENERAL: 0.75, ModelCapability.CODING: 0.7},
        "phi-3": {ModelCapability.REASONING: 0.85, ModelCapability.GENERAL: 0.8, ModelCapability.CODING: 0.75},
        "phi-4": {ModelCapability.REASONING: 0.9, ModelCapability.GENERAL: 0.85, ModelCapability.CODING: 0.8},
        "gemma": {ModelCapability.GENERAL: 0.8, ModelCapability.REASONING: 0.75, ModelCapability.CREATIVE: 0.7},
        "gemma-2": {ModelCapability.GENERAL: 0.85, ModelCapability.REASONING: 0.8, ModelCapability.CREATIVE: 0.75},
        "yi": {ModelCapability.GENERAL: 0.85, ModelCapability.REASONING: 0.8, ModelCapability.CREATIVE: 0.75},
        "deepseek": {ModelCapability.REASONING: 0.9, ModelCapability.GENERAL: 0.85, ModelCapability.CODING: 0.75},
        "deepseek-v2": {ModelCapability.REASONING: 0.9, ModelCapability.GENERAL: 0.85, ModelCapability.CODING: 0.8},
        "internlm": {ModelCapability.GENERAL: 0.8, ModelCapability.REASONING: 0.8, ModelCapability.CODING: 0.7},
        "solar": {ModelCapability.GENERAL: 0.85, ModelCapability.REASONING: 0.8, ModelCapability.CREATIVE: 0.75},
        "openchat": {ModelCapability.GENERAL: 0.85, ModelCapability.REASONING: 0.8, ModelCapability.CREATIVE: 0.7},
        "neural-chat": {ModelCapability.GENERAL: 0.8, ModelCapability.REASONING: 0.75, ModelCapability.CREATIVE: 0.7},
        "zephyr": {ModelCapability.GENERAL: 0.85, ModelCapability.REASONING: 0.8, ModelCapability.CREATIVE: 0.75},
        "starling": {ModelCapability.GENERAL: 0.85, ModelCapability.REASONING: 0.85, ModelCapability.CREATIVE: 0.7},

        # Creative/writing models
        "creative": {ModelCapability.CREATIVE: 0.9, ModelCapability.GENERAL: 0.7},
        "writer": {ModelCapability.CREATIVE: 0.9, ModelCapability.GENERAL: 0.75},
        "story": {ModelCapability.CREATIVE: 0.85, ModelCapability.GENERAL: 0.7},
        "novel": {ModelCapability.CREATIVE: 0.85, ModelCapability.GENERAL: 0.65},
        "mythomax": {ModelCapability.CREATIVE: 0.9, ModelCapability.GENERAL: 0.75},
        "nous-hermes": {ModelCapability.CREATIVE: 0.85, ModelCapability.GENERAL: 0.8, ModelCapability.REASONING: 0.8},

        # Analysis models
        "analyst": {ModelCapability.ANALYSIS: 0.9, ModelCapability.REASONING: 0.85, ModelCapability.GENERAL: 0.7},
        "orca": {ModelCapability.REASONING: 0.85, ModelCapability.ANALYSIS: 0.8, ModelCapability.GENERAL: 0.75},
        "wizard": {ModelCapability.REASONING: 0.85, ModelCapability.GENERAL: 0.8},
        "wizardlm": {ModelCapability.REASONING: 0.85, ModelCapability.GENERAL: 0.8, ModelCapability.CREATIVE: 0.7},
    }

    # HuggingFace tags -> capabilities
    TAG_MAPPING: dict[str, dict[ModelCapability, float]] = {
        "code": {ModelCapability.CODING: 0.85},
        "code-generation": {ModelCapability.CODING: 0.9},
        "text-generation": {ModelCapability.GENERAL: 0.7},
        "conversational": {ModelCapability.GENERAL: 0.75},
        "math": {ModelCapability.MATH: 0.85},
        "reasoning": {ModelCapability.REASONING: 0.8},
        "creative-writing": {ModelCapability.CREATIVE: 0.85},
        "story-generation": {ModelCapability.CREATIVE: 0.8},
        "question-answering": {ModelCapability.GENERAL: 0.75, ModelCapability.REASONING: 0.7},
        "summarization": {ModelCapability.ANALYSIS: 0.75, ModelCapability.GENERAL: 0.7},
    }

    # Keywords in description -> capabilities
    DESCRIPTION_KEYWORDS: dict[str, dict[ModelCapability, float]] = {
        "code": {ModelCapability.CODING: 0.7},
        "coding": {ModelCapability.CODING: 0.75},
        "programming": {ModelCapability.CODING: 0.75},
        "developer": {ModelCapability.CODING: 0.7},
        "software": {ModelCapability.CODING: 0.65},
        "math": {ModelCapability.MATH: 0.7},
        "mathematical": {ModelCapability.MATH: 0.75},
        "arithmetic": {ModelCapability.MATH: 0.7},
        "calculation": {ModelCapability.MATH: 0.65},
        "reasoning": {ModelCapability.REASONING: 0.7},
        "logic": {ModelCapability.REASONING: 0.7},
        "analytical": {ModelCapability.REASONING: 0.65, ModelCapability.ANALYSIS: 0.7},
        "creative": {ModelCapability.CREATIVE: 0.7},
        "storytelling": {ModelCapability.CREATIVE: 0.75},
        "writing": {ModelCapability.CREATIVE: 0.65},
        "fiction": {ModelCapability.CREATIVE: 0.7},
        "roleplay": {ModelCapability.CREATIVE: 0.7},
        "general": {ModelCapability.GENERAL: 0.7},
        "instruction": {ModelCapability.GENERAL: 0.7},
        "assistant": {ModelCapability.GENERAL: 0.7},
        "chat": {ModelCapability.GENERAL: 0.7},
    }

    # Default capabilities when nothing specific is detected
    DEFAULT_CAPABILITIES: dict[ModelCapability, float] = {
        ModelCapability.GENERAL: 0.7,
    }

    def detect(
        self,
        repo_id: str,
        tags: Optional[list[str]] = None,
        description: Optional[str] = None,
    ) -> dict[ModelCapability, float]:
        """
        Automatically detect capabilities from model metadata.

        Args:
            repo_id: HuggingFace repository ID (e.g., "TheBloke/CodeLlama-7B-GGUF")
            tags: Optional list of HuggingFace tags
            description: Optional model card description

        Returns:
            Dict of capability -> score (0.0 - 1.0)
        """
        capabilities: dict[ModelCapability, float] = {}

        # 1. Check repo name against known patterns
        repo_caps = self._detect_from_repo_name(repo_id)
        self._merge_capabilities(capabilities, repo_caps)

        # 2. Check HuggingFace tags
        if tags:
            tag_caps = self._detect_from_tags(tags)
            self._merge_capabilities(capabilities, tag_caps)

        # 3. Parse description for keywords
        if description:
            desc_caps = self._detect_from_description(description)
            self._merge_capabilities(capabilities, desc_caps)

        # 4. If nothing detected, use defaults
        if not capabilities:
            logger.info(f"No specific capabilities detected for {repo_id}, using defaults")
            capabilities = self.DEFAULT_CAPABILITIES.copy()

        # Ensure we always have a general capability
        if ModelCapability.GENERAL not in capabilities:
            capabilities[ModelCapability.GENERAL] = 0.6

        logger.info(f"Detected capabilities for {repo_id}: {self._format_caps(capabilities)}")
        return capabilities

    def _detect_from_repo_name(self, repo_id: str) -> dict[ModelCapability, float]:
        """Check repo name against known patterns."""
        capabilities: dict[ModelCapability, float] = {}

        # Normalize: lowercase, replace separators with spaces
        name = repo_id.lower().replace("/", " ").replace("-", " ").replace("_", " ")

        # Check each pattern (longer patterns first for specificity)
        sorted_patterns = sorted(self.PATTERNS.keys(), key=len, reverse=True)

        for pattern in sorted_patterns:
            # Normalize pattern the same way (replace hyphens with spaces)
            pattern_normalized = pattern.replace("-", " ")
            # Check if pattern words appear in sequence in the name
            if pattern_normalized in name:
                self._merge_capabilities(capabilities, self.PATTERNS[pattern])
                logger.debug(f"Pattern '{pattern}' matched in repo name")
                break  # Use first (most specific) match

        return capabilities

    def _detect_from_tags(self, tags: list[str]) -> dict[ModelCapability, float]:
        """Check HuggingFace tags for capability hints."""
        capabilities: dict[ModelCapability, float] = {}

        for tag in tags:
            tag_lower = tag.lower().strip()
            if tag_lower in self.TAG_MAPPING:
                self._merge_capabilities(capabilities, self.TAG_MAPPING[tag_lower])

        return capabilities

    def _detect_from_description(self, description: str) -> dict[ModelCapability, float]:
        """Parse description for capability keywords."""
        capabilities: dict[ModelCapability, float] = {}

        desc_lower = description.lower()

        for keyword, caps in self.DESCRIPTION_KEYWORDS.items():
            if keyword in desc_lower:
                # Lower weight for description keywords (less reliable)
                weighted_caps = {k: v * 0.8 for k, v in caps.items()}
                self._merge_capabilities(capabilities, weighted_caps)

        return capabilities

    def _merge_capabilities(
        self,
        target: dict[ModelCapability, float],
        source: dict[ModelCapability, float],
    ) -> None:
        """Merge capabilities, keeping the higher score for each."""
        for cap, score in source.items():
            if cap not in target or score > target[cap]:
                target[cap] = score

    def _format_caps(self, capabilities: dict[ModelCapability, float]) -> str:
        """Format capabilities for logging."""
        return ", ".join(
            f"{cap.value}={score:.2f}"
            for cap, score in sorted(capabilities.items(), key=lambda x: -x[1])
        )

    def detect_from_repo_id_only(self, repo_id: str) -> dict[ModelCapability, float]:
        """
        Quick detection using only repo ID.
        Useful when HuggingFace metadata isn't available.
        """
        return self.detect(repo_id)


# Singleton instance for convenience
_detector: Optional[CapabilityDetector] = None


def get_detector() -> CapabilityDetector:
    """Get the singleton CapabilityDetector instance."""
    global _detector
    if _detector is None:
        _detector = CapabilityDetector()
    return _detector


def detect_capabilities(
    repo_id: str,
    tags: Optional[list[str]] = None,
    description: Optional[str] = None,
) -> dict[ModelCapability, float]:
    """
    Convenience function for capability detection.

    Example:
        caps = detect_capabilities("TheBloke/CodeLlama-7B-GGUF")
        # Returns: {ModelCapability.CODING: 0.95, ModelCapability.REASONING: 0.7, ...}
    """
    return get_detector().detect(repo_id, tags, description)
