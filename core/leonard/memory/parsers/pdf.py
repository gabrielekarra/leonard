"""Parser for PDF documents."""

from pathlib import Path

from leonard.memory.parsers.base import DocumentParser, ParsedDocument, DocumentSection
from leonard.utils.logging import logger


class PDFParser(DocumentParser):
    """
    Parser for PDF documents using pypdf.

    Extracts text content from PDF files.
    Supports: .pdf
    """

    @property
    def supported_extensions(self) -> list[str]:
        return [".pdf"]

    async def parse(self, file_path: Path) -> ParsedDocument:
        """
        Parse a PDF file.

        Args:
            file_path: Path to the PDF file

        Returns:
            ParsedDocument with extracted text content
        """
        self._validate_file(file_path)

        metadata = self._get_base_metadata(file_path)
        metadata["language"] = "pdf"

        try:
            from pypdf import PdfReader

            reader = PdfReader(str(file_path))

            # Extract text from all pages
            pages = []
            sections = []

            for i, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    pages.append(page_text)
                    sections.append(
                        DocumentSection(
                            title=f"Page {i + 1}",
                            content=page_text.strip(),
                            level=1,
                        )
                    )

            content = "\n\n".join(pages)

            # Extract PDF metadata
            if reader.metadata:
                if reader.metadata.title:
                    metadata["title"] = reader.metadata.title
                if reader.metadata.author:
                    metadata["author"] = reader.metadata.author
                if reader.metadata.subject:
                    metadata["subject"] = reader.metadata.subject

            metadata["page_count"] = len(reader.pages)

            logger.info(f"Parsed PDF: {file_path.name} ({len(reader.pages)} pages)")

            return ParsedDocument(
                content=content,
                metadata=metadata,
                sections=sections,
            )

        except ImportError:
            raise RuntimeError(
                "pypdf is required for PDF parsing. "
                "Install with: pip install pypdf"
            )
        except Exception as e:
            logger.error(f"Failed to parse PDF {file_path}: {e}")
            raise RuntimeError(f"Failed to parse PDF: {e}")
