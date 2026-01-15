"""
Embedding model wrapper for RAG.
Uses sentence-transformers with a small, efficient model.
"""

from pathlib import Path
from typing import Optional

import numpy as np

from leonard.utils.logging import logger


class EmbeddingModel:
    """
    Local embedding model using sentence-transformers.

    Uses all-MiniLM-L6-v2 by default:
    - 384-dimensional embeddings
    - ~90MB model size
    - Fast inference on CPU/GPU
    """

    MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIM = 384

    def __init__(self, model_name: Optional[str] = None, cache_dir: Optional[Path] = None):
        """
        Initialize the embedding model.

        Args:
            model_name: HuggingFace model name (default: all-MiniLM-L6-v2)
            cache_dir: Directory to cache the model (default: ~/.leonard/embeddings)
        """
        self.model_name = model_name or self.MODEL_NAME
        self.cache_dir = cache_dir or Path.home() / ".leonard" / "embeddings"
        self._model = None
        self._initialized = False

    async def initialize(self) -> None:
        """
        Download and load the embedding model.
        This is done lazily on first use.
        """
        if self._initialized:
            return

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Loading embedding model: {self.model_name}")

        try:
            from sentence_transformers import SentenceTransformer

            # Load model with caching
            self._model = SentenceTransformer(
                self.model_name,
                cache_folder=str(self.cache_dir),
            )

            self._initialized = True
            logger.info(f"Embedding model loaded successfully (dim={self.EMBEDDING_DIM})")

        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise RuntimeError(f"Could not load embedding model: {e}")

    def embed(self, texts: list[str]) -> np.ndarray:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            numpy array of shape (len(texts), EMBEDDING_DIM)
        """
        if not self._initialized or self._model is None:
            raise RuntimeError("Embedding model not initialized. Call initialize() first.")

        if not texts:
            return np.array([])

        # Generate embeddings
        embeddings = self._model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=True,  # L2 normalize for cosine similarity
        )

        return embeddings

    def embed_query(self, query: str) -> np.ndarray:
        """
        Embed a single query string.
        Optimized path for single queries.

        Args:
            query: Query string to embed

        Returns:
            numpy array of shape (EMBEDDING_DIM,)
        """
        if not self._initialized or self._model is None:
            raise RuntimeError("Embedding model not initialized. Call initialize() first.")

        embedding = self._model.encode(
            query,
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=True,
        )

        return embedding

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        """
        Embed texts in batches for memory efficiency with large document sets.

        Args:
            texts: List of text strings to embed
            batch_size: Number of texts per batch

        Returns:
            numpy array of shape (len(texts), EMBEDDING_DIM)
        """
        if not self._initialized or self._model is None:
            raise RuntimeError("Embedding model not initialized. Call initialize() first.")

        if not texts:
            return np.array([])

        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = self._model.encode(
                batch,
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            all_embeddings.append(batch_embeddings)

        return np.vstack(all_embeddings)

    @property
    def is_initialized(self) -> bool:
        """Check if the model is initialized."""
        return self._initialized

    @property
    def embedding_dim(self) -> int:
        """Get the embedding dimension."""
        return self.EMBEDDING_DIM
