"""Document parsers for various file formats."""

from leonard.memory.parsers.base import DocumentParser, ParsedDocument
from leonard.memory.parsers.text import TextParser
from leonard.memory.parsers.code import CodeParser
from leonard.memory.parsers.pdf import PDFParser
from leonard.memory.parsers.docx import DocxParser
from leonard.memory.parsers.spreadsheet import SpreadsheetParser

# Registry of all parsers
ALL_PARSERS: list[type[DocumentParser]] = [
    TextParser,
    CodeParser,
    PDFParser,
    DocxParser,
    SpreadsheetParser,
]


def get_parser_for_file(file_path: str) -> DocumentParser | None:
    """
    Get the appropriate parser for a file based on its extension.

    Args:
        file_path: Path to the file

    Returns:
        Parser instance or None if no parser supports this file type
    """
    ext = file_path.lower().rsplit(".", 1)[-1] if "." in file_path else ""

    for parser_class in ALL_PARSERS:
        parser = parser_class()
        if f".{ext}" in parser.supported_extensions:
            return parser

    return None


__all__ = [
    "DocumentParser",
    "ParsedDocument",
    "TextParser",
    "CodeParser",
    "PDFParser",
    "DocxParser",
    "SpreadsheetParser",
    "ALL_PARSERS",
    "get_parser_for_file",
]
