"""Base class for document parsers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class DocumentSection:
    """A section of a document (e.g., heading, paragraph)."""

    title: Optional[str]
    content: str
    level: int = 0  # Heading level (0 = body text)


@dataclass
class ParsedDocument:
    """Result of parsing a document."""

    content: str  # Full text content
    metadata: dict = field(default_factory=dict)
    sections: list[DocumentSection] = field(default_factory=list)

    @property
    def source(self) -> str:
        """Get the source file path."""
        return self.metadata.get("source", "unknown")

    @property
    def file_type(self) -> str:
        """Get the file type."""
        return self.metadata.get("file_type", "unknown")


class DocumentParser(ABC):
    """
    Abstract base class for document parsers.

    Each parser handles one or more file types and converts them
    to a standardized ParsedDocument format.
    """

    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """
        List of supported file extensions (including the dot).

        Example: [".txt", ".md"]
        """
        pass

    @abstractmethod
    async def parse(self, file_path: Path) -> ParsedDocument:
        """
        Parse a document and return structured content.

        Args:
            file_path: Path to the file to parse

        Returns:
            ParsedDocument containing the extracted content and metadata

        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If the file type is not supported
            RuntimeError: If parsing fails
        """
        pass

    def _validate_file(self, file_path: Path) -> None:
        """
        Validate that the file exists and is a supported type.

        Args:
            file_path: Path to validate

        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If the file type is not supported
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = file_path.suffix.lower()
        if ext not in self.supported_extensions:
            raise ValueError(
                f"Unsupported file type: {ext}. "
                f"Supported: {self.supported_extensions}"
            )

    def _get_base_metadata(self, file_path: Path) -> dict:
        """
        Get basic metadata from file path.

        Args:
            file_path: Path to the file

        Returns:
            Dictionary of base metadata
        """
        return {
            "source": str(file_path.resolve()),
            "filename": file_path.name,
            "extension": file_path.suffix.lower(),
            "file_type": file_path.suffix.lower().lstrip("."),
            "size_bytes": file_path.stat().st_size if file_path.exists() else 0,
        }
