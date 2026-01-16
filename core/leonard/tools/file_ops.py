"""
Verified filesystem operations used by Leonard tools.
Each operation performs strict path resolution, guarded execution, and post-action verification.
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterable

from leonard.tools.base import ToolResult, VerificationResult
from leonard.tools.verifier import FilesystemVerifier
from leonard.utils.logging import logger

# Only operate within user-controlled locations
ALLOWED_ROOTS = [Path.home().resolve(), Path("/tmp").resolve()]
PROTECTED_PATHS = {
    Path("/"),
    Path("/Users"),
    Path("/System"),
    Path("/Library"),
    Path("/Applications"),
    Path.home().resolve(),
}


def _ensure_allowed(path: Path) -> Path:
    """Resolve and enforce the path is inside an allowed root to prevent traversal."""
    resolved = path.expanduser().resolve()
    if not any(resolved == root or resolved.is_relative_to(root) for root in ALLOWED_ROOTS):
        raise PermissionError(f"Path {resolved} is outside allowed roots")
    return resolved


def _human_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / 1024 / 1024:.1f} MB"


def _verification_failure(details: str, action: str, changed: Iterable[str]) -> ToolResult:
    changed_list = list(changed)
    return ToolResult(
        status="error",
        action=action,
        output=None,
        error=details,
        before_paths=changed_list,
        after_paths=[],
        changed=changed_list,
        verification=VerificationResult(passed=False, details=details),
        verification_passed=False,
        verification_details=details,
        message_user=details,
        message_internal=details,
    )


def _permission_denied_message(path: str, exc: Exception | None = None) -> str:
    suffix = f" ({exc})" if exc else ""
    return (
        f"macOS blocked access to {path}. Grant Full Disk Access to Leonard (or the terminal) and retry."
        f"{suffix}"
    )


class FileOperations:
    """Filesystem helpers with verification."""

    @staticmethod
    def read_file(path: str, max_lines: int = 100, max_bytes: int = 10 * 1024 * 1024) -> ToolResult:
        try:
            file_path = _ensure_allowed(Path(path))
            if not file_path.exists():
                return _verification_failure(f"File not found: {file_path}", "read", [str(file_path)])
            if not file_path.is_file():
                return _verification_failure(f"Not a file: {file_path}", "read", [str(file_path)])

            size = file_path.stat().st_size
            if size > max_bytes:
                return _verification_failure(
                    f"File too large ({_human_size(size)}). Maximum is {_human_size(max_bytes)}",
                    "read",
                    [str(file_path)],
                )

            lines: list[str] = []
            with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
                for i, line in enumerate(handle):
                    if i >= max_lines:
                        lines.append(f"... (truncated at {max_lines} lines)")
                        break
                    lines.append(line.rstrip("\n"))

            return ToolResult(
                status="success",
                action="read",
                output={"path": str(file_path), "lines": lines},
                before_paths=[],
                after_paths=[],
                changed=[],
                verification=VerificationResult(True, "Read-only operation"),
                verification_passed=True,
                verification_details="Read-only operation",
                message_user=f"Read {len(lines)} lines from {file_path}",
            )
        except PermissionError as exc:
            return _verification_failure(_permission_denied_message(path, exc), "read", [path])
        except Exception as exc:  # pragma: no cover - unexpected failure guard
            logger.error(f"Failed to read file {path}: {exc}")
            return _verification_failure(f"Unexpected error reading {path}: {exc}", "read", [path])

    @staticmethod
    def list_directory(path: str, show_hidden: bool = False) -> ToolResult:
        try:
            dir_path = _ensure_allowed(Path(path))
            if not dir_path.exists():
                return _verification_failure(f"Directory not found: {dir_path}", "list", [str(dir_path)])
            if not dir_path.is_dir():
                return _verification_failure(f"Not a directory: {dir_path}", "list", [str(dir_path)])

            items = []
            for item in sorted(dir_path.iterdir()):
                if not show_hidden and item.name.startswith("."):
                    continue
                item_type = "dir" if item.is_dir() else "file"
                size = item.stat().st_size if item.is_file() else 0
                items.append(
                    {
                        "name": item.name,
                        "type": item_type,
                        "size_bytes": size,
                    }
                )

            return ToolResult(
                status="success",
                action="list",
                output={"path": str(dir_path), "items": items},
                before_paths=[],
                after_paths=[],
                changed=[],
                verification=VerificationResult(True, "Read-only operation"),
                verification_passed=True,
                verification_details="Read-only operation",
                message_user=f"Found {len(items)} item(s) in {dir_path}",
            )
        except PermissionError as exc:
            return _verification_failure(_permission_denied_message(path, exc), "list", [path])
        except Exception as exc:  # pragma: no cover - unexpected failure guard
            logger.error(f"Failed to list directory {path}: {exc}")
            return _verification_failure(f"Unexpected error listing {path}: {exc}", "list", [path])

    @staticmethod
    def write_file(path: str, content: str, append: bool = False) -> ToolResult:
        try:
            target = _ensure_allowed(Path(path))
            target.parent.mkdir(parents=True, exist_ok=True)
            existed_before = target.exists()

            incoming = (content or "").encode("utf-8")
            combined: bytes
            if append and target.exists():
                existing = target.read_bytes()
                combined = existing + incoming
            else:
                combined = incoming

            with tempfile.NamedTemporaryFile(delete=False, dir=target.parent) as tmp:
                tmp.write(combined)
                tmp.flush()
                os.fsync(tmp.fileno())
                temp_name = tmp.name

            os.replace(temp_name, target)

            verification = FilesystemVerifier.verify_write(target, combined)
            status = "success" if verification.passed else "error"
            action = "append" if append else "write"
            return ToolResult(
                status=status,
                action=action,
                output={
                    "path": str(target),
                    "bytes_written": len(incoming),
                    "total_bytes": len(combined),
                },
                error=None if verification.passed else verification.details,
                before_paths=[str(target)] if existed_before else [],
                after_paths=[str(target)],
                changed=[str(target)],
                verification=verification,
                verification_passed=verification.passed,
                verification_details=verification.details,
                message_user=(
                    f"{'Appended to' if append else 'Wrote'} {target} (verified)"
                    if verification.passed
                    else verification.details
                ),
            )
        except PermissionError as exc:
            return _verification_failure(_permission_denied_message(path, exc), "write", [path])
        except Exception as exc:  # pragma: no cover - unexpected failure guard
            logger.error(f"Failed to write file {path}: {exc}")
            return _verification_failure(f"Unexpected error writing {path}: {exc}", "write", [path])

    @staticmethod
    def move_file(source: str, destination: str) -> ToolResult:
        try:
            src_path = _ensure_allowed(Path(source))
            dst_path = _ensure_allowed(Path(destination))

            if not src_path.exists():
                return _verification_failure(f"Source not found: {src_path}", "move", [str(src_path), str(dst_path)])

            dst_path.parent.mkdir(parents=True, exist_ok=True)
            expected_size = src_path.stat().st_size if src_path.is_file() else None
            shutil.move(str(src_path), str(dst_path))

            verification = FilesystemVerifier.verify_move(src_path, dst_path, expected_size)
            status = "success" if verification.passed else "error"

            return ToolResult(
                status=status,
                action="move",
                output={"source": str(src_path), "destination": str(dst_path)},
                error=None if verification.passed else verification.details,
                before_paths=[str(src_path)],
                after_paths=[str(dst_path)],
                changed=[str(src_path), str(dst_path)],
                verification=verification,
                verification_passed=verification.passed,
                verification_details=verification.details,
                message_user=(
                    f"Moved {src_path.name} to {dst_path}" if verification.passed else verification.details
                ),
            )
        except PermissionError as exc:
            return _verification_failure(_permission_denied_message(source, exc), "move", [source, destination])
        except Exception as exc:  # pragma: no cover - unexpected failure guard
            logger.error(f"Failed to move file {source} -> {destination}: {exc}")
            return _verification_failure(f"Unexpected error moving file: {exc}", "move", [source, destination])

    @staticmethod
    def copy_file(source: str, destination: str) -> ToolResult:
        try:
            src_path = _ensure_allowed(Path(source))
            dst_path = _ensure_allowed(Path(destination))

            if not src_path.exists():
                return _verification_failure(f"Source not found: {src_path}", "copy", [str(src_path), str(dst_path)])

            dst_path.parent.mkdir(parents=True, exist_ok=True)
            if src_path.is_dir():
                shutil.copytree(str(src_path), str(dst_path))
                expected_size = None
            else:
                shutil.copy2(str(src_path), str(dst_path))
                expected_size = src_path.stat().st_size

            verification = FilesystemVerifier.verify_copy(src_path, dst_path, expected_size)
            status = "success" if verification.passed else "error"

            return ToolResult(
                status=status,
                action="copy",
                output={"source": str(src_path), "destination": str(dst_path)},
                error=None if verification.passed else verification.details,
                before_paths=[str(src_path)],
                after_paths=[str(dst_path)],
                changed=[str(src_path), str(dst_path)],
                verification=verification,
                verification_passed=verification.passed,
                verification_details=verification.details,
                message_user=(
                    f"Copied {src_path.name} to {dst_path}" if verification.passed else verification.details
                ),
            )
        except PermissionError as exc:
            return _verification_failure(_permission_denied_message(source, exc), "copy", [source, destination])
        except Exception as exc:  # pragma: no cover - unexpected failure guard
            logger.error(f"Failed to copy file {source} -> {destination}: {exc}")
            return _verification_failure(f"Unexpected error copying file: {exc}", "copy", [source, destination])

    @staticmethod
    def delete_file(path: str) -> ToolResult:
        try:
            target = _ensure_allowed(Path(path))
            if not target.exists():
                return _verification_failure(f"Path not found: {target}", "delete", [str(target)])

            for dangerous in PROTECTED_PATHS:
                if target == dangerous:
                    return _verification_failure(f"Cannot delete protected path: {target}", "delete", [str(target)])

            if target.is_dir():
                shutil.rmtree(str(target))
            else:
                target.unlink()

            verification = FilesystemVerifier.verify_delete(target)
            status = "success" if verification.passed else "error"

            return ToolResult(
                status=status,
                action="delete",
                output={"path": str(target)},
                error=None if verification.passed else verification.details,
                before_paths=[str(target)],
                after_paths=[],
                changed=[str(target)],
                verification=verification,
                verification_passed=verification.passed,
                verification_details=verification.details,
                message_user=(f"Deleted {target}" if verification.passed else verification.details),
            )
        except PermissionError as exc:
            return _verification_failure(_permission_denied_message(path, exc), "delete", [path])
        except Exception as exc:  # pragma: no cover - unexpected failure guard
            logger.error(f"Failed to delete path {path}: {exc}")
            return _verification_failure(f"Unexpected error deleting {path}: {exc}", "delete", [path])

    @staticmethod
    def delete_by_pattern(directory: str, pattern: str) -> ToolResult:
        try:
            dir_path = _ensure_allowed(Path(directory))
            if not dir_path.exists() or not dir_path.is_dir():
                return _verification_failure(f"Directory not found: {dir_path}", "delete", [str(dir_path)])

            patterns = [p.strip() for p in pattern.split(",") if p.strip()]
            deleted: list[str] = []
            failures: list[str] = []

            for pat in patterns:
                for match in dir_path.glob(pat):
                    if not match.is_file():
                        continue
                    try:
                        match.unlink()
                        if match.exists():
                            failures.append(match.name)
                        else:
                            deleted.append(match.name)
                    except Exception as exc:  # pragma: no cover - defensive
                        failures.append(f"{match.name}: {exc}")

            verification = VerificationResult(
                passed=not failures,
                details="All matching files removed" if not failures else f"Failed to remove: {', '.join(failures)}",
            )

            status = "success" if verification.passed else "error"
            return ToolResult(
                status=status,
                action="delete",
                output={
                    "directory": str(dir_path),
                    "pattern": pattern,
                    "deleted": deleted,
                    "failed": failures,
                },
                error=None if verification.passed else verification.details,
                before_paths=[str(dir_path / name) for name in deleted],
                after_paths=[],
                changed=[str(dir_path / name) for name in deleted],
                verification=verification,
                verification_passed=verification.passed,
                verification_details=verification.details,
                message_user=(
                    f"Deleted {len(deleted)} file(s) matching '{pattern}'"
                    if verification.passed
                    else f"Could not delete some files: {verification.details}"
                ),
            )
        except PermissionError as exc:
            return _verification_failure(_permission_denied_message(directory, exc), "delete", [directory])
        except Exception as exc:  # pragma: no cover - unexpected failure guard
            logger.error(f"Failed to delete by pattern in {directory}: {exc}")
            return _verification_failure(f"Unexpected error deleting files: {exc}", "delete", [directory])

    @staticmethod
    def create_directory(path: str) -> ToolResult:
        try:
            dir_path = _ensure_allowed(Path(path))
            if dir_path.exists():
                return _verification_failure(f"Path already exists: {dir_path}", "create_directory", [str(dir_path)])

            dir_path.mkdir(parents=True, exist_ok=True)
            verification = FilesystemVerifier.verify_create_dir(dir_path)
            status = "success" if verification.passed else "error"

            return ToolResult(
                status=status,
                action="create",
                output={"path": str(dir_path)},
                error=None if verification.passed else verification.details,
                before_paths=[],
                after_paths=[str(dir_path)],
                changed=[str(dir_path)],
                verification=verification,
                verification_passed=verification.passed,
                verification_details=verification.details,
                message_user=(f"Created folder {dir_path}" if verification.passed else verification.details),
            )
        except PermissionError as exc:
            return _verification_failure(_permission_denied_message(path, exc), "create", [path])
        except Exception as exc:  # pragma: no cover - unexpected failure guard
            logger.error(f"Failed to create directory {path}: {exc}")
            return _verification_failure(f"Unexpected error creating directory: {exc}", "create", [path])

    @staticmethod
    def search_files(directory: str, pattern: str, max_results: int = 50) -> ToolResult:
        try:
            dir_path = _ensure_allowed(Path(directory))
            if not dir_path.exists():
                return _verification_failure(f"Directory not found: {dir_path}", "search", [str(dir_path)])

            matches: list[str] = []
            for match in dir_path.glob(pattern):
                if len(matches) >= max_results:
                    break
                matches.append(str(match))

            return ToolResult(
                status="success",
                action="search",
                output={"matches": matches, "count": len(matches), "truncated": len(matches) >= max_results},
                before_paths=[],
                after_paths=[],
                changed=[],
                verification=VerificationResult(True, "Read-only operation"),
                verification_passed=True,
                verification_details="Read-only operation",
                message_user=f"Found {len(matches)} matching item(s)",
            )
        except PermissionError as exc:
            return _verification_failure(_permission_denied_message(directory, exc), "search", [directory])
        except Exception as exc:  # pragma: no cover - unexpected failure guard
            logger.error(f"Failed to search files in {directory}: {exc}")
            return _verification_failure(f"Unexpected error searching files: {exc}", "search", [directory])
