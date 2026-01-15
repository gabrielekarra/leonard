"""
Manages model inference using llama-cpp-python directly.
Each model is loaded into memory and inference runs in the main process.
Native macOS with Metal GPU acceleration.
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import AsyncGenerator, Optional

from leonard.utils.logging import logger


class ProcessStatus(Enum):
    """Status of a model."""

    STOPPED = "stopped"
    LOADING = "loading"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class ModelInstance:
    """Represents a loaded model instance."""

    model_id: str
    model_path: Path
    llm: any  # Llama instance
    status: ProcessStatus = ProcessStatus.STOPPED
    error_message: Optional[str] = None


class ProcessManager:
    """
    Manages llama-cpp-python model instances.
    Models are loaded directly into memory for inference.
    Supports Metal GPU acceleration on macOS.
    """

    def __init__(self):
        self.models: dict[str, ModelInstance] = {}
        self._lock = asyncio.Lock()

    # ─────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────

    async def start(
        self,
        model_id: str,
        model_path: Path,
        n_ctx: int = 4096,
        n_gpu_layers: int = -1,  # -1 = all layers on Metal GPU
    ) -> ModelInstance:
        """
        Load a model into memory.

        Args:
            model_id: Unique identifier for this model
            model_path: Path to .gguf file
            n_ctx: Context window size
            n_gpu_layers: GPU layers (-1 = all on GPU, 0 = CPU only)

        Returns:
            ModelInstance with status info
        """
        async with self._lock:
            # If already running, return existing
            if model_id in self.models:
                existing = self.models[model_id]
                if existing.status == ProcessStatus.RUNNING:
                    logger.info(f"Model {model_id} already loaded")
                    return existing
                # If error/stopped, clean up first
                await self._unload_model(model_id)

            if not model_path.exists():
                raise FileNotFoundError(f"Model not found: {model_path}")

            logger.info(f"Loading {model_id} from {model_path}...")

            instance = ModelInstance(
                model_id=model_id,
                model_path=model_path,
                llm=None,
                status=ProcessStatus.LOADING,
            )
            self.models[model_id] = instance

        # Load model in thread pool to avoid blocking
        try:
            llm = await self._load_model(model_path, n_ctx, n_gpu_layers)

            async with self._lock:
                instance.llm = llm
                instance.status = ProcessStatus.RUNNING
                logger.info(f"Model {model_id} loaded successfully")

            return instance

        except Exception as e:
            async with self._lock:
                instance.status = ProcessStatus.ERROR
                instance.error_message = str(e)
            logger.error(f"Failed to load {model_id}: {e}")
            raise

    async def _load_model(
        self, model_path: Path, n_ctx: int, n_gpu_layers: int
    ):
        """Load model in thread pool."""
        from llama_cpp import Llama

        loop = asyncio.get_event_loop()

        def do_load():
            try:
                return Llama(
                    model_path=str(model_path),
                    n_ctx=n_ctx,
                    n_gpu_layers=n_gpu_layers,
                    verbose=False,
                )
            except Exception as e:
                logger.error(f"Failed to load model {model_path}: {e}")
                raise RuntimeError(f"Model loading failed: {e}") from e

        return await loop.run_in_executor(None, do_load)

    async def _unload_model(self, model_id: str):
        """Unload a model from memory."""
        if model_id in self.models:
            instance = self.models[model_id]
            if instance.llm is not None:
                # Delete the model to free memory
                # Catch any destructor errors from llama-cpp-python
                try:
                    del instance.llm
                except Exception as e:
                    logger.warning(f"Error during model cleanup: {e}")
                instance.llm = None
            instance.status = ProcessStatus.STOPPED
            del self.models[model_id]

    async def stop(self, model_id: str) -> bool:
        """Stop/unload a model."""
        async with self._lock:
            if model_id not in self.models:
                return False

            logger.info(f"Unloading {model_id}...")
            await self._unload_model(model_id)
            logger.info(f"Unloaded {model_id}")
            return True

    async def stop_all(self):
        """Stop all models."""
        async with self._lock:
            for model_id in list(self.models.keys()):
                await self._unload_model(model_id)

    # ─────────────────────────────────────────────────────────
    # INFERENCE
    # ─────────────────────────────────────────────────────────

    async def chat(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        """
        Chat completion (non-streaming).

        Args:
            model_id: ID of loaded model
            messages: List of {"role": "user"|"assistant"|"system", "content": "..."}
            max_tokens: Max tokens to generate
            temperature: Sampling temperature

        Returns:
            Generated response content
        """
        instance = self._get_running(model_id)

        # Run inference in thread pool
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: instance.llm.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            ),
        )

        return response["choices"][0]["message"]["content"]

    async def chat_stream(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """
        Chat completion with streaming.
        Yields content chunks as they're generated.

        Args:
            model_id: ID of loaded model
            messages: List of message dicts
            max_tokens: Max tokens to generate
            temperature: Sampling temperature

        Yields:
            Content chunks as strings
        """
        instance = self._get_running(model_id)

        # Create streaming response in thread
        loop = asyncio.get_event_loop()

        # We need to handle streaming differently - use a queue
        import queue
        q: queue.Queue = queue.Queue()

        def generate():
            try:
                for chunk in instance.llm.create_chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True,
                ):
                    delta = chunk["choices"][0].get("delta", {})
                    if "content" in delta:
                        q.put(delta["content"])
                q.put(None)  # Signal completion
            except Exception as e:
                q.put(e)

        # Start generation in background thread
        import threading
        thread = threading.Thread(target=generate)
        thread.start()

        # Yield chunks as they arrive
        while True:
            # Check queue with small timeout to allow asyncio
            try:
                item = await loop.run_in_executor(
                    None, lambda: q.get(timeout=0.1)
                )
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
            except queue.Empty:
                continue

        thread.join()

    def _get_running(self, model_id: str) -> ModelInstance:
        """Get a running model instance or raise error."""
        if model_id not in self.models:
            raise ValueError(f"Model {model_id} not loaded. Call start() first.")

        instance = self.models[model_id]

        if instance.status != ProcessStatus.RUNNING:
            raise RuntimeError(
                f"Model {model_id} is {instance.status.value}: {instance.error_message}"
            )

        if instance.llm is None:
            raise RuntimeError(f"Model {model_id} has no LLM instance")

        return instance

    # ─────────────────────────────────────────────────────────
    # STATUS
    # ─────────────────────────────────────────────────────────

    def is_running(self, model_id: str) -> bool:
        """Check if model is loaded and running."""
        return (
            model_id in self.models
            and self.models[model_id].status == ProcessStatus.RUNNING
        )

    def list_running(self) -> list[str]:
        """List IDs of loaded models."""
        return [
            model_id
            for model_id, instance in self.models.items()
            if instance.status == ProcessStatus.RUNNING
        ]

    def get_status(self, model_id: str) -> Optional[dict]:
        """Get status of a model."""
        if model_id not in self.models:
            return None

        instance = self.models[model_id]
        return {
            "model_id": instance.model_id,
            "status": instance.status.value,
            "model_path": str(instance.model_path),
            "error": instance.error_message,
        }
