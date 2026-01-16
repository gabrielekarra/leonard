"""
Memory Manager using LlamaIndex.
Provides document indexing and RAG retrieval with a simple toggle interface.
"""

import json
from pathlib import Path
from leonard.utils.logging import logger


class MemoryManager:
    """
    Manages document memory using LlamaIndex.
    Auto-indexes Documents, Desktop, and Downloads when enabled.
    """

    INDEX_DIR = Path.home() / ".leonard" / "index"
    SETTINGS_FILE = Path.home() / ".leonard" / "memory_settings.json"
    INDEX_METADATA_FILE = INDEX_DIR / "index_metadata.json"
    AUTO_FOLDERS = ["Documents", "Desktop", "Downloads"]

    def __init__(self):
        self.enabled = False
        self.indexed = False
        self.index = None
        self.embed_model = None
        self._indexing = False
        self.indexed_files: list[str] = []

    async def initialize(self):
        """Initialize the memory manager."""
        self._load_settings()
        if self.enabled:
            await self._load_or_build_index()

    def _load_settings(self):
        """Load settings from disk."""
        if self.SETTINGS_FILE.exists():
            try:
                with open(self.SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                    self.enabled = data.get("enabled", False)
            except Exception as e:
                logger.warning(f"Failed to load memory settings: {e}")
                self.enabled = False

        self._load_index_metadata()

    def _load_index_metadata(self) -> None:
        """Load indexed file metadata from disk."""
        if self.INDEX_METADATA_FILE.exists():
            try:
                with open(self.INDEX_METADATA_FILE, "r") as f:
                    data = json.load(f)
                    self.indexed_files = data.get("indexed_files", [])
            except Exception as e:
                logger.warning(f"Failed to load index metadata: {e}")
                self.indexed_files = []

    def _save_index_metadata(self) -> None:
        """Persist indexed file metadata to disk."""
        try:
            self.INDEX_DIR.mkdir(parents=True, exist_ok=True)
            with open(self.INDEX_METADATA_FILE, "w") as f:
                json.dump({"indexed_files": self.indexed_files}, f)
        except Exception as e:
            logger.warning(f"Failed to save index metadata: {e}")

    def _save_settings(self):
        """Save settings to disk."""
        try:
            self.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.SETTINGS_FILE, "w") as f:
                json.dump({"enabled": self.enabled}, f)
        except Exception as e:
            logger.error(f"Failed to save memory settings: {e}")

    async def toggle(self, enabled: bool) -> bool:
        """Toggle memory on/off."""
        self.enabled = enabled
        self._save_settings()

        if enabled and not self.index:
            await self._load_or_build_index()
        elif not enabled:
            self.index = None
            self.indexed = False

        return self.enabled

    async def _load_or_build_index(self):
        """Load existing index or build a new one."""
        if self._indexing:
            return

        self._indexing = True
        try:
            # Lazy import LlamaIndex to avoid startup overhead
            from llama_index.core import StorageContext, load_index_from_storage
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding

            # Initialize embedding model
            if not self.embed_model:
                logger.info("Loading embedding model...")
                self.embed_model = HuggingFaceEmbedding(model_name="all-MiniLM-L6-v2")

            if self.INDEX_DIR.exists() and (self.INDEX_DIR / "docstore.json").exists():
                # Load existing index
                logger.info("Loading existing index...")
                storage_context = StorageContext.from_defaults(persist_dir=str(self.INDEX_DIR))
                self.index = load_index_from_storage(
                    storage_context, embed_model=self.embed_model
                )
                self.indexed = True
            else:
                # Build new index
                await self._rebuild_index()

            if self.indexed and not self.indexed_files:
                self._load_index_metadata()
            logger.info("Index loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load/build index: {e}")
            self.index = None
            self.indexed = False
        finally:
            self._indexing = False

    async def _rebuild_index(self):
        """Rebuild the index from auto-folders."""
        try:
            from llama_index.core import VectorStoreIndex, SimpleDirectoryReader

            logger.info("Building new index from user folders...")

            # Collect documents from all auto-folders
            all_documents = []
            home = Path.home()

            for folder_name in self.AUTO_FOLDERS:
                folder_path = home / folder_name
                if folder_path.exists() and folder_path.is_dir():
                    logger.info(f"Indexing {folder_path}...")
                    try:
                        reader = SimpleDirectoryReader(
                            input_dir=str(folder_path),
                            recursive=True,
                            exclude_hidden=True,
                            errors="ignore",
                        )
                        docs = reader.load_data()
                        all_documents.extend(docs)
                        logger.info(f"Loaded {len(docs)} documents from {folder_name}")
                    except Exception as e:
                        logger.warning(f"Error reading {folder_name}: {e}")

            if not all_documents:
                logger.warning("No documents found to index")
                self.indexed = False
                return

            # Build the index
            logger.info(f"Building index from {len(all_documents)} documents...")
            self.index = VectorStoreIndex.from_documents(
                all_documents, embed_model=self.embed_model
            )

            # Persist to disk
            self.INDEX_DIR.mkdir(parents=True, exist_ok=True)
            self.index.storage_context.persist(persist_dir=str(self.INDEX_DIR))
            self.indexed = True
            self.indexed_files = self._extract_indexed_files(all_documents)
            self._save_index_metadata()
            logger.info("Index built and persisted successfully")

        except Exception as e:
            logger.error(f"Failed to rebuild index: {e}")
            self.index = None
            self.indexed = False

    async def reindex(self):
        """Force rebuild the index."""
        # Clear existing index
        if self.INDEX_DIR.exists():
            import shutil
            shutil.rmtree(self.INDEX_DIR)

        self.index = None
        self.indexed = False
        self.indexed_files = []

        if self.enabled:
            await self._rebuild_index()

    async def get_context_for_query(self, query: str, max_chars: int = 2000) -> str:
        """
        Retrieve relevant context for a query.
        Returns formatted context string for prompt injection.

        Args:
            query: The user's query
            max_chars: Maximum characters to return (default 2000 to fit in small context windows)
        """
        if not self.enabled or not self.index:
            return ""

        try:
            retriever = self.index.as_retriever(similarity_top_k=3)
            nodes = retriever.retrieve(query)

            if not nodes:
                return ""

            # Format context with source citations, respecting max_chars
            context_parts = []
            total_chars = 0

            for node in nodes:
                source = node.metadata.get("file_name", "unknown")
                text = node.text.strip()[:500]  # Limit each chunk
                if text:
                    part = f"[{source}]: {text}"
                    if total_chars + len(part) > max_chars:
                        break
                    context_parts.append(part)
                    total_chars += len(part)

            context = "\n\n".join(context_parts)
            logger.info(f"Retrieved {len(context_parts)} relevant chunks ({total_chars} chars)")
            return context

        except Exception as e:
            logger.error(f"Failed to retrieve context: {e}")
            return ""

    def get_status(self) -> dict:
        """Get current memory status."""
        return {
            "enabled": self.enabled,
            "indexed": self.indexed,
            "indexing": self._indexing,
            "indexed_count": len(self.indexed_files),
            "indexed_files": self.indexed_files,
        }

    def _extract_indexed_files(self, documents: list) -> list[str]:
        """Extract file paths from indexed documents."""
        files = []
        for doc in documents:
            metadata = getattr(doc, "metadata", {}) or {}
            path = metadata.get("file_path") or metadata.get("file_name")
            if path:
                files.append(path)
        return sorted(set(files))

    async def shutdown(self):
        """Clean shutdown."""
        self.index = None
        self.embed_model = None
        logger.info("Memory manager shut down")
