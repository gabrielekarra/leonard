"""
Document indexer for processing and embedding content.
Handles file parsing, chunking, and storage in the vault.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from leonard.memory.chunking import get_chunker_for_file, DocumentChunk
from leonard.memory.parsers import get_parser_for_file
from leonard.memory.vault import Vault
from leonard.utils.logging import logger


@dataclass
class IndexResult:
    """Result of an indexing operation."""

    success: bool
    source: str
    chunks_indexed: int
    error: Optional[str] = None
    duration_seconds: float = 0.0


@dataclass
class IndexingStatus:
    """Status of the indexing queue."""

    is_indexing: bool
    queue_size: int
    current_file: Optional[str]
    files_indexed: int
    files_failed: int


class Indexer:
    """
    Document indexer with parser registry and chunking.

    Processes files through:
    1. Parsing (extract text based on file type)
    2. Chunking (split into overlapping chunks)
    3. Storage (embed and store in vault)
    """

    # File extensions to skip
    SKIP_EXTENSIONS = {
        ".pyc", ".pyo", ".so", ".dll", ".dylib",  # Compiled
        ".zip", ".tar", ".gz", ".rar", ".7z",  # Archives
        ".exe", ".bin", ".dat",  # Binary
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",  # Images
        ".mp3", ".wav", ".ogg", ".flac",  # Audio
        ".mp4", ".avi", ".mov", ".mkv",  # Video
        ".ttf", ".otf", ".woff", ".woff2",  # Fonts
        ".lock", ".log",  # Lock and log files
    }

    # Directories to skip
    SKIP_DIRS = {
        "__pycache__", ".git", ".svn", ".hg",
        "node_modules", ".venv", "venv", "env",
        ".idea", ".vscode", ".DS_Store",
        "build", "dist", "target", ".next",
    }

    def __init__(self, vault: Vault):
        """
        Initialize the indexer.

        Args:
            vault: Vault instance for storage
        """
        self.vault = vault
        self._index_queue: asyncio.Queue = asyncio.Queue()
        self._indexing_task: Optional[asyncio.Task] = None
        self._is_indexing = False
        self._current_file: Optional[str] = None
        self._files_indexed = 0
        self._files_failed = 0

        logger.info("Indexer initialized")

    async def index_file(
        self,
        file_path: Path,
        force_reindex: bool = False,
    ) -> IndexResult:
        """
        Index a single file.

        Args:
            file_path: Path to the file to index
            force_reindex: If True, reindex even if already indexed

        Returns:
            IndexResult with status and statistics
        """
        start_time = datetime.now()
        file_path = Path(file_path).resolve()

        # Check if file should be skipped
        if self._should_skip_file(file_path):
            return IndexResult(
                success=False,
                source=str(file_path),
                chunks_indexed=0,
                error="File type not supported",
            )

        # Get appropriate parser
        parser = get_parser_for_file(str(file_path))
        if not parser:
            return IndexResult(
                success=False,
                source=str(file_path),
                chunks_indexed=0,
                error=f"No parser for file type: {file_path.suffix}",
            )

        try:
            # Delete existing chunks if reindexing
            if force_reindex:
                await self.vault.delete_by_source(str(file_path))

            # Parse the document
            logger.info(f"Parsing: {file_path.name}")
            parsed_doc = await parser.parse(file_path)

            if not parsed_doc.content.strip():
                return IndexResult(
                    success=True,
                    source=str(file_path),
                    chunks_indexed=0,
                    error="File is empty",
                )

            # Get appropriate chunker
            chunker = get_chunker_for_file(str(file_path))

            # Chunk the document
            chunks = chunker.chunk(parsed_doc.content, parsed_doc.metadata)

            if not chunks:
                return IndexResult(
                    success=True,
                    source=str(file_path),
                    chunks_indexed=0,
                    error="No chunks generated",
                )

            # Store in vault
            await self.vault.store(chunks)

            duration = (datetime.now() - start_time).total_seconds()

            logger.info(
                f"Indexed: {file_path.name} ({len(chunks)} chunks in {duration:.2f}s)"
            )

            return IndexResult(
                success=True,
                source=str(file_path),
                chunks_indexed=len(chunks),
                duration_seconds=duration,
            )

        except Exception as e:
            logger.error(f"Failed to index {file_path}: {e}")
            return IndexResult(
                success=False,
                source=str(file_path),
                chunks_indexed=0,
                error=str(e),
            )

    async def index_directory(
        self,
        directory: Path,
        recursive: bool = True,
        patterns: Optional[list[str]] = None,
        force_reindex: bool = False,
    ) -> list[IndexResult]:
        """
        Index all supported files in a directory.

        Args:
            directory: Directory to index
            recursive: If True, index subdirectories
            patterns: Optional glob patterns to match (e.g., ["*.py", "*.md"])
            force_reindex: If True, reindex even if already indexed

        Returns:
            List of IndexResult for each file
        """
        directory = Path(directory).expanduser().resolve()

        if not directory.exists():
            return [
                IndexResult(
                    success=False,
                    source=str(directory),
                    chunks_indexed=0,
                    error="Directory does not exist",
                )
            ]

        if not directory.is_dir():
            return [
                IndexResult(
                    success=False,
                    source=str(directory),
                    chunks_indexed=0,
                    error="Path is not a directory",
                )
            ]

        # Collect files to index
        files_to_index = []

        if patterns:
            # Use specific patterns
            for pattern in patterns:
                if recursive:
                    files_to_index.extend(directory.rglob(pattern))
                else:
                    files_to_index.extend(directory.glob(pattern))
        else:
            # Index all supported files
            if recursive:
                files_to_index = [
                    f for f in directory.rglob("*")
                    if f.is_file() and not self._should_skip_file(f)
                ]
            else:
                files_to_index = [
                    f for f in directory.glob("*")
                    if f.is_file() and not self._should_skip_file(f)
                ]

        logger.info(f"Found {len(files_to_index)} files to index in {directory}")

        # Index each file
        results = []
        for file_path in files_to_index:
            result = await self.index_file(file_path, force_reindex=force_reindex)
            results.append(result)

            if result.success:
                self._files_indexed += 1
            else:
                self._files_failed += 1

        return results

    async def index_text(
        self,
        text: str,
        source: str,
        metadata: Optional[dict] = None,
    ) -> IndexResult:
        """
        Index raw text content.

        Args:
            text: Text content to index
            source: Source identifier (e.g., URL, note title)
            metadata: Optional additional metadata

        Returns:
            IndexResult with status
        """
        if not text.strip():
            return IndexResult(
                success=False,
                source=source,
                chunks_indexed=0,
                error="Text is empty",
            )

        try:
            # Create metadata
            doc_metadata = metadata or {}
            doc_metadata["source"] = source
            doc_metadata["file_type"] = "text"

            # Chunk the text
            from leonard.memory.chunking import TextChunker
            chunker = TextChunker()
            chunks = chunker.chunk(text, doc_metadata)

            if not chunks:
                return IndexResult(
                    success=True,
                    source=source,
                    chunks_indexed=0,
                    error="No chunks generated",
                )

            # Store in vault
            await self.vault.store(chunks)

            logger.info(f"Indexed text from {source} ({len(chunks)} chunks)")

            return IndexResult(
                success=True,
                source=source,
                chunks_indexed=len(chunks),
            )

        except Exception as e:
            logger.error(f"Failed to index text from {source}: {e}")
            return IndexResult(
                success=False,
                source=source,
                chunks_indexed=0,
                error=str(e),
            )

    async def remove_source(self, source_path: str) -> int:
        """
        Remove a source from the index.

        Args:
            source_path: Path of the source to remove

        Returns:
            Number of chunks removed
        """
        return await self.vault.delete_by_source(source_path)

    async def start_background_indexing(self) -> None:
        """Start background worker for processing index queue."""
        if self._indexing_task is not None:
            return

        self._indexing_task = asyncio.create_task(self._process_queue())
        logger.info("Background indexing started")

    async def stop_background_indexing(self) -> None:
        """Stop background indexing worker."""
        if self._indexing_task is not None:
            self._indexing_task.cancel()
            try:
                await self._indexing_task
            except asyncio.CancelledError:
                pass
            self._indexing_task = None
            logger.info("Background indexing stopped")

    async def queue_file(self, file_path: Path) -> None:
        """Add a file to the indexing queue."""
        await self._index_queue.put(("file", file_path))

    async def queue_directory(
        self, directory: Path, recursive: bool = True
    ) -> None:
        """Add a directory to the indexing queue."""
        await self._index_queue.put(("directory", directory, recursive))

    def get_status(self) -> IndexingStatus:
        """Get current indexing status."""
        return IndexingStatus(
            is_indexing=self._is_indexing,
            queue_size=self._index_queue.qsize(),
            current_file=self._current_file,
            files_indexed=self._files_indexed,
            files_failed=self._files_failed,
        )

    async def _process_queue(self) -> None:
        """Process items from the indexing queue."""
        while True:
            try:
                item = await self._index_queue.get()
                self._is_indexing = True

                if item[0] == "file":
                    file_path = item[1]
                    self._current_file = str(file_path)
                    await self.index_file(file_path)

                elif item[0] == "directory":
                    directory = item[1]
                    recursive = item[2] if len(item) > 2 else True
                    self._current_file = str(directory)
                    await self.index_directory(directory, recursive=recursive)

                self._index_queue.task_done()
                self._current_file = None
                self._is_indexing = False

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing index queue: {e}")
                self._is_indexing = False

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if a file should be skipped."""
        # Check extension
        if file_path.suffix.lower() in self.SKIP_EXTENSIONS:
            return True

        # Check if in skip directory
        for part in file_path.parts:
            if part in self.SKIP_DIRS:
                return True

        # Check if hidden file (starts with .)
        if file_path.name.startswith("."):
            return True

        # Check if file is too large (> 10MB)
        try:
            if file_path.stat().st_size > 10 * 1024 * 1024:
                return True
        except OSError:
            return True

        return False
