"""
File organizer tool for Leonard.
Automatically organizes files into categorized folders.
"""

import shutil
from pathlib import Path

from leonard.tools.base import Tool, ToolResult, ToolParameter, ToolCategory, RiskLevel
from leonard.utils.logging import logger


# File categorization rules
CATEGORIES = {
    "Code": {
        "extensions": [".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c", ".h", ".go", ".rs", ".rb", ".php", ".swift", ".kt"],
        "keywords": ["def ", "function ", "class ", "import ", "const ", "var ", "let ", "#include"],
    },
    "Documents": {
        "extensions": [".txt", ".doc", ".docx", ".pdf", ".rtf", ".odt", ".md"],
        "keywords": ["meeting", "notes", "report", "letter", "memo", "dear ", "summary"],
    },
    "Receipts": {
        "extensions": [],
        "keywords": ["receipt", "invoice", "order", "payment", "total:", "$", "€", "amount due", "paid"],
    },
    "Images": {
        "extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff"],
        "keywords": ["[image", "photo", "picture", "screenshot"],
    },
    "Videos": {
        "extensions": [".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv"],
        "keywords": [],
    },
    "Audio": {
        "extensions": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"],
        "keywords": [],
    },
    "Archives": {
        "extensions": [".zip", ".tar", ".gz", ".rar", ".7z", ".bz2"],
        "keywords": [],
    },
    "Data": {
        "extensions": [".json", ".xml", ".csv", ".yaml", ".yml", ".sql", ".db"],
        "keywords": [],
    },
}


def categorize_file(filepath: Path) -> str:
    """Determine the category for a file based on extension and content."""
    ext = filepath.suffix.lower()
    filename = filepath.name.lower()

    # First check by extension
    for category, rules in CATEGORIES.items():
        if ext in rules["extensions"]:
            return category

    # Then check by content keywords
    try:
        if ext in [".txt", ".md", ".py", ".js", ".ts", ".json", ".xml", ".csv", ".html", ".css"]:
            content = filepath.read_text(errors="ignore")[:1000].lower()

            for category, rules in CATEGORIES.items():
                for keyword in rules["keywords"]:
                    if keyword.lower() in content or keyword.lower() in filename:
                        return category
    except Exception:
        pass

    # Check filename for keywords
    for category, rules in CATEGORIES.items():
        for keyword in rules["keywords"]:
            if keyword.lower() in filename:
                return category

    return "Other"


class OrganizeFilesTool(Tool):
    """Organize files in a directory into categorized subfolders."""

    def __init__(self):
        super().__init__(
            name="organize_files",
            description="Organize files in a directory into categorized subfolders (Code, Documents, Images, Receipts, etc.) based on file type and content",
            category=ToolCategory.FILESYSTEM,
            risk_level=RiskLevel.MEDIUM,
            parameters=[
                ToolParameter(
                    name="directory",
                    type="string",
                    description="Path to the directory to organize",
                    required=True,
                ),
            ],
        )

    async def execute(self, directory: str) -> ToolResult:
        """Organize files into categorized folders."""
        try:
            dir_path = Path(directory).expanduser().resolve()

            if not dir_path.exists():
                return ToolResult(success=False, output=None, error=f"Directory not found: {directory}")

            if not dir_path.is_dir():
                return ToolResult(success=False, output=None, error=f"Not a directory: {directory}")

            # Get list of files (not directories)
            files = [f for f in dir_path.iterdir() if f.is_file()]

            if not files:
                return ToolResult(success=False, output=None, error="No files to organize")

            # Categorize each file
            file_categories: dict[str, list[Path]] = {}
            for file in files:
                category = categorize_file(file)
                if category not in file_categories:
                    file_categories[category] = []
                file_categories[category].append(file)

            # Create folders and move files
            moved_files = []
            created_folders = []

            for category, cat_files in file_categories.items():
                if not cat_files:
                    continue

                # Create category folder
                cat_folder = dir_path / category
                if not cat_folder.exists():
                    cat_folder.mkdir()
                    created_folders.append(category)

                # Move files
                for file in cat_files:
                    dest = cat_folder / file.name
                    # Handle name conflicts
                    if dest.exists():
                        base = file.stem
                        ext = file.suffix
                        counter = 1
                        while dest.exists():
                            dest = cat_folder / f"{base}_{counter}{ext}"
                            counter += 1

                    shutil.move(str(file), str(dest))
                    moved_files.append(f"{file.name} → {category}/")

            # Build result message
            result_lines = [f"Organized {len(moved_files)} files in {directory}:"]
            result_lines.append("")

            if created_folders:
                result_lines.append(f"Created folders: {', '.join(created_folders)}")
                result_lines.append("")

            for category in sorted(file_categories.keys()):
                cat_files = file_categories[category]
                if cat_files:
                    result_lines.append(f"📁 {category}/ ({len(cat_files)} files)")
                    for f in cat_files[:5]:
                        result_lines.append(f"   • {f.name}")
                    if len(cat_files) > 5:
                        result_lines.append(f"   ... and {len(cat_files) - 5} more")

            logger.info(f"Organized {len(moved_files)} files into {len(file_categories)} categories")

            return ToolResult(
                success=True,
                output="\n".join(result_lines),
                error=None
            )

        except PermissionError:
            return ToolResult(success=False, output=None, error=f"Permission denied: {directory}")
        except Exception as e:
            logger.error(f"Failed to organize files: {e}")
            return ToolResult(success=False, output=None, error=str(e))


# Export tools
ORGANIZER_TOOLS = [OrganizeFilesTool()]
