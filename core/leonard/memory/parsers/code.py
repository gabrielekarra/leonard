"""Parser for code files with syntax awareness."""

import re
from pathlib import Path

from leonard.memory.parsers.base import DocumentParser, ParsedDocument, DocumentSection


class CodeParser(DocumentParser):
    """
    Parser for source code files.

    Extracts docstrings, comments, and function signatures.
    Supports: .py, .js, .ts, .jsx, .tsx, .json, .yaml, .yml
    """

    # Language detection by extension
    LANGUAGE_MAP = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".java": "java",
        ".cpp": "cpp",
        ".c": "c",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".kt": "kotlin",
        ".sh": "bash",
        ".sql": "sql",
        ".html": "html",
        ".css": "css",
    }

    @property
    def supported_extensions(self) -> list[str]:
        return list(self.LANGUAGE_MAP.keys())

    async def parse(self, file_path: Path) -> ParsedDocument:
        """
        Parse a code file.

        Args:
            file_path: Path to the file

        Returns:
            ParsedDocument with code content and extracted sections
        """
        self._validate_file(file_path)

        content = self._read_file(file_path)
        metadata = self._get_base_metadata(file_path)

        # Detect language
        ext = file_path.suffix.lower()
        language = self.LANGUAGE_MAP.get(ext, "unknown")
        metadata["language"] = language

        # Extract sections (functions, classes, etc.)
        sections = self._extract_code_sections(content, language)

        return ParsedDocument(
            content=content,
            metadata=metadata,
            sections=sections,
        )

    def _read_file(self, file_path: Path) -> str:
        """Read file content with encoding detection."""
        encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]

        for encoding in encodings:
            try:
                return file_path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue

        return file_path.read_text(encoding="utf-8", errors="ignore")

    def _extract_code_sections(
        self, content: str, language: str
    ) -> list[DocumentSection]:
        """
        Extract meaningful sections from code.

        Args:
            content: Code content
            language: Programming language

        Returns:
            List of DocumentSection objects
        """
        sections = []

        if language == "python":
            sections = self._extract_python_sections(content)
        elif language in ("javascript", "typescript"):
            sections = self._extract_js_sections(content)
        else:
            # Generic extraction based on comments
            sections = self._extract_generic_sections(content)

        return sections

    def _extract_python_sections(self, content: str) -> list[DocumentSection]:
        """Extract sections from Python code."""
        sections = []

        # Match class definitions
        class_pattern = r'class\s+(\w+)(?:\([^)]*\))?:\s*(?:"""([^"]*?)""")?'
        for match in re.finditer(class_pattern, content, re.DOTALL):
            class_name = match.group(1)
            docstring = match.group(2) or ""
            sections.append(
                DocumentSection(
                    title=f"class {class_name}",
                    content=docstring.strip(),
                    level=1,
                )
            )

        # Match function definitions
        func_pattern = r'def\s+(\w+)\([^)]*\)(?:\s*->\s*[^:]+)?:\s*(?:"""([^"]*?)""")?'
        for match in re.finditer(func_pattern, content, re.DOTALL):
            func_name = match.group(1)
            docstring = match.group(2) or ""
            sections.append(
                DocumentSection(
                    title=f"def {func_name}",
                    content=docstring.strip(),
                    level=2,
                )
            )

        # Extract module docstring
        module_doc = re.match(r'^\s*"""([^"]*?)"""', content, re.DOTALL)
        if module_doc:
            sections.insert(
                0,
                DocumentSection(
                    title="Module",
                    content=module_doc.group(1).strip(),
                    level=0,
                ),
            )

        return sections

    def _extract_js_sections(self, content: str) -> list[DocumentSection]:
        """Extract sections from JavaScript/TypeScript code."""
        sections = []

        # Match class definitions
        class_pattern = r'class\s+(\w+)(?:\s+extends\s+\w+)?\s*\{'
        for match in re.finditer(class_pattern, content):
            class_name = match.group(1)
            sections.append(
                DocumentSection(
                    title=f"class {class_name}",
                    content="",
                    level=1,
                )
            )

        # Match function definitions
        func_patterns = [
            r'function\s+(\w+)\s*\([^)]*\)',  # function name() {}
            r'const\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>',  # const name = () =>
            r'const\s+(\w+)\s*=\s*(?:async\s*)?function',  # const name = function
        ]

        for pattern in func_patterns:
            for match in re.finditer(pattern, content):
                func_name = match.group(1)
                sections.append(
                    DocumentSection(
                        title=f"function {func_name}",
                        content="",
                        level=2,
                    )
                )

        # Extract JSDoc comments
        jsdoc_pattern = r'/\*\*\s*\n([^*]*(?:\*(?!/)[^*]*)*)\*/'
        for match in re.finditer(jsdoc_pattern, content):
            doc_content = match.group(1)
            # Clean up the JSDoc content
            doc_lines = [
                line.strip().lstrip("*").strip()
                for line in doc_content.split("\n")
            ]
            doc_text = "\n".join(line for line in doc_lines if line)
            if doc_text:
                sections.append(
                    DocumentSection(
                        title="Documentation",
                        content=doc_text,
                        level=0,
                    )
                )

        return sections

    def _extract_generic_sections(self, content: str) -> list[DocumentSection]:
        """Generic section extraction based on comments."""
        sections = []

        # Look for block comments
        block_comment_patterns = [
            r'/\*\s*\n?([^*]*(?:\*(?!/)[^*]*)*)\*/',  # /* ... */
            r'"""([^"]*?)"""',  # """ ... """
            r"'''([^']*?)'''",  # ''' ... '''
        ]

        for pattern in block_comment_patterns:
            for match in re.finditer(pattern, content, re.DOTALL):
                comment = match.group(1).strip()
                if len(comment) > 20:  # Only include substantial comments
                    sections.append(
                        DocumentSection(
                            title="Comment",
                            content=comment,
                            level=0,
                        )
                    )

        return sections
