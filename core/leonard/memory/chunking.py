"""
Text chunking strategies for document processing.
Splits documents into overlapping chunks for embedding and retrieval.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DocumentChunk:
    """A chunk of text from a document."""

    content: str
    metadata: dict
    chunk_index: int
    start_char: int
    end_char: int

    @property
    def source(self) -> str:
        """Get the source file path."""
        return self.metadata.get("source", "unknown")


@dataclass
class ChunkingConfig:
    """Configuration for text chunking."""

    chunk_size: int = 1000  # Characters per chunk (~250 tokens)
    chunk_overlap: int = 200  # Overlap between chunks
    separators: list[str] = field(
        default_factory=lambda: ["\n\n", "\n", ". ", " ", ""]
    )
    min_chunk_size: int = 100  # Minimum chunk size to keep


class TextChunker:
    """
    Recursive character text splitter.
    Splits text by trying separators in order of preference.
    """

    def __init__(self, config: Optional[ChunkingConfig] = None):
        self.config = config or ChunkingConfig()

    def chunk(self, text: str, metadata: dict) -> list[DocumentChunk]:
        """
        Split text into overlapping chunks.

        Args:
            text: The text to split
            metadata: Metadata to attach to each chunk

        Returns:
            List of DocumentChunk objects
        """
        if not text.strip():
            return []

        chunks = self._split_text(text, self.config.separators)
        return self._create_chunks(chunks, text, metadata)

    def _split_text(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split text using separators."""
        final_chunks = []
        separator = separators[0] if separators else ""
        new_separators = separators[1:] if len(separators) > 1 else []

        # Split by current separator
        if separator:
            splits = text.split(separator)
        else:
            # Character-level split as fallback
            splits = list(text)

        # Process each split
        current_chunk = ""
        for split in splits:
            piece = split + separator if separator else split

            if len(current_chunk) + len(piece) <= self.config.chunk_size:
                current_chunk += piece
            else:
                if current_chunk:
                    # If current chunk is too big and we have more separators, recurse
                    if len(current_chunk) > self.config.chunk_size and new_separators:
                        final_chunks.extend(self._split_text(current_chunk, new_separators))
                    else:
                        final_chunks.append(current_chunk.rstrip(separator))
                current_chunk = piece

        # Don't forget the last chunk
        if current_chunk:
            if len(current_chunk) > self.config.chunk_size and new_separators:
                final_chunks.extend(self._split_text(current_chunk, new_separators))
            else:
                final_chunks.append(current_chunk.rstrip(separator))

        return final_chunks

    def _create_chunks(
        self, texts: list[str], original_text: str, metadata: dict
    ) -> list[DocumentChunk]:
        """Create DocumentChunk objects with overlap."""
        if not texts:
            return []

        chunks = []
        current_pos = 0

        for i, text in enumerate(texts):
            # Find position in original text
            start_pos = original_text.find(text, current_pos)
            if start_pos == -1:
                start_pos = current_pos
            end_pos = start_pos + len(text)

            # Skip chunks that are too small
            if len(text.strip()) < self.config.min_chunk_size:
                current_pos = end_pos
                continue

            # Add overlap from previous chunk
            if i > 0 and start_pos > 0:
                overlap_start = max(0, start_pos - self.config.chunk_overlap)
                overlap_text = original_text[overlap_start:start_pos]
                # Find a good break point in the overlap
                for sep in ["\n", ". ", " "]:
                    if sep in overlap_text:
                        idx = overlap_text.rfind(sep)
                        overlap_text = overlap_text[idx + len(sep):]
                        break
                text = overlap_text + text

            chunk = DocumentChunk(
                content=text.strip(),
                metadata={**metadata, "chunk_index": len(chunks)},
                chunk_index=len(chunks),
                start_char=start_pos,
                end_char=end_pos,
            )
            chunks.append(chunk)
            current_pos = end_pos

        return chunks


class CodeChunker(TextChunker):
    """
    Code-aware chunker that tries to preserve logical code units.
    Respects function and class boundaries where possible.
    """

    def __init__(self, config: Optional[ChunkingConfig] = None):
        # Code typically needs larger chunks to preserve context
        code_config = config or ChunkingConfig(
            chunk_size=1500,
            chunk_overlap=100,
            separators=[
                "\n\nclass ",  # Class definitions
                "\n\ndef ",  # Function definitions
                "\n\nasync def ",  # Async function definitions
                "\n\n",  # Double newline (paragraphs)
                "\n",  # Single newline
                " ",  # Space
                "",  # Character
            ],
        )
        super().__init__(code_config)

    def chunk(self, text: str, metadata: dict) -> list[DocumentChunk]:
        """
        Split code into chunks, preserving logical units.

        Args:
            text: The code to split
            metadata: Metadata to attach to each chunk

        Returns:
            List of DocumentChunk objects
        """
        if not text.strip():
            return []

        # Detect language from metadata
        language = metadata.get("language", "")
        file_ext = metadata.get("extension", "")

        # Adjust separators based on language
        if language in ("python", "py") or file_ext == ".py":
            self.config.separators = [
                "\n\nclass ",
                "\n\ndef ",
                "\n\nasync def ",
                "\n\n",
                "\n",
                " ",
                "",
            ]
        elif language in ("javascript", "typescript", "js", "ts") or file_ext in (
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
        ):
            self.config.separators = [
                "\n\nclass ",
                "\n\nfunction ",
                "\n\nconst ",
                "\n\nexport ",
                "\n\n",
                "\n",
                " ",
                "",
            ]

        return super().chunk(text, metadata)


class MarkdownChunker(TextChunker):
    """
    Markdown-aware chunker that respects heading structure.
    """

    def __init__(self, config: Optional[ChunkingConfig] = None):
        md_config = config or ChunkingConfig(
            chunk_size=1000,
            chunk_overlap=150,
            separators=[
                "\n## ",  # H2 headings
                "\n### ",  # H3 headings
                "\n#### ",  # H4 headings
                "\n\n",  # Paragraphs
                "\n",  # Lines
                ". ",  # Sentences
                " ",  # Words
                "",  # Characters
            ],
        )
        super().__init__(md_config)


def get_chunker_for_file(file_path: str) -> TextChunker:
    """
    Get the appropriate chunker based on file extension.

    Args:
        file_path: Path to the file

    Returns:
        Appropriate TextChunker subclass
    """
    ext = file_path.lower().rsplit(".", 1)[-1] if "." in file_path else ""

    code_extensions = {"py", "js", "ts", "jsx", "tsx", "java", "cpp", "c", "go", "rs", "rb"}
    markdown_extensions = {"md", "markdown"}

    if ext in code_extensions:
        return CodeChunker()
    elif ext in markdown_extensions:
        return MarkdownChunker()
    else:
        return TextChunker()
