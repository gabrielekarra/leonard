"""Parser for text and markdown files."""

import re
from pathlib import Path

from leonard.memory.parsers.base import DocumentParser, ParsedDocument, DocumentSection


class TextParser(DocumentParser):
    """
    Parser for plain text and markdown files.

    Supports: .txt, .md, .markdown, .rst, .text
    """

    @property
    def supported_extensions(self) -> list[str]:
        return [".txt", ".md", ".markdown", ".rst", ".text"]

    async def parse(self, file_path: Path) -> ParsedDocument:
        """
        Parse a text or markdown file.

        Args:
            file_path: Path to the file

        Returns:
            ParsedDocument with content and sections (for markdown)
        """
        self._validate_file(file_path)

        # Read file content
        content = self._read_file(file_path)
        metadata = self._get_base_metadata(file_path)

        # Extract sections for markdown files
        sections = []
        if file_path.suffix.lower() in [".md", ".markdown"]:
            sections = self._extract_markdown_sections(content)
            metadata["language"] = "markdown"

        return ParsedDocument(
            content=content,
            metadata=metadata,
            sections=sections,
        )

    def _read_file(self, file_path: Path) -> str:
        """
        Read file content with encoding detection.

        Args:
            file_path: Path to the file

        Returns:
            File content as string
        """
        # Try common encodings
        encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]

        for encoding in encodings:
            try:
                return file_path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue

        # Fallback: read with errors ignored
        return file_path.read_text(encoding="utf-8", errors="ignore")

    def _extract_markdown_sections(self, content: str) -> list[DocumentSection]:
        """
        Extract sections from markdown content based on headings.

        Args:
            content: Markdown content

        Returns:
            List of DocumentSection objects
        """
        sections = []
        lines = content.split("\n")
        current_section = None
        current_content = []

        for line in lines:
            # Check for markdown heading
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)

            if heading_match:
                # Save previous section
                if current_section or current_content:
                    sections.append(
                        DocumentSection(
                            title=current_section,
                            content="\n".join(current_content).strip(),
                            level=len(heading_match.group(1)) if current_section else 0,
                        )
                    )

                current_section = heading_match.group(2).strip()
                current_content = []
            else:
                current_content.append(line)

        # Don't forget the last section
        if current_section or current_content:
            sections.append(
                DocumentSection(
                    title=current_section,
                    content="\n".join(current_content).strip(),
                    level=0,
                )
            )

        return sections
