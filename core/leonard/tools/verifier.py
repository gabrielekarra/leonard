"""
Filesystem verification helpers for Leonard tool executions.
All mutations should be verified here after execution.
"""

from pathlib import Path

from leonard.tools.base import VerificationResult


class FilesystemVerifier:
    """Post-operation verification for filesystem mutations."""

    @staticmethod
    def verify_write(path: Path, expected: bytes) -> VerificationResult:
        if not path.exists():
            return VerificationResult(False, f"{path} missing after write")
        try:
            actual = path.read_bytes()
            if actual != expected:
                return VerificationResult(False, f"{path} contents differ after write")
        except Exception as exc:  # pragma: no cover - defensive
            return VerificationResult(False, f"Could not verify contents: {exc}")
        return VerificationResult(True, f"{path} verified ({len(expected)} bytes)")

    @staticmethod
    def verify_move(source: Path, destination: Path, expected_size: int | None) -> VerificationResult:
        if source.exists():
            return VerificationResult(False, f"Source still present after move: {source}")
        if not destination.exists():
            return VerificationResult(False, f"Destination missing after move: {destination}")
        if expected_size is not None and destination.is_file():
            dest_size = destination.stat().st_size
            if dest_size != expected_size:
                return VerificationResult(False, f"Destination size mismatch ({dest_size} vs {expected_size})")
        return VerificationResult(True, "Move verified")

    @staticmethod
    def verify_copy(source: Path, destination: Path, expected_size: int | None) -> VerificationResult:
        if not destination.exists():
            return VerificationResult(False, f"Destination missing after copy: {destination}")
        if not source.exists():
            return VerificationResult(False, f"Source disappeared during copy: {source}")
        if expected_size is not None and destination.is_file():
            dest_size = destination.stat().st_size
            if dest_size != expected_size:
                return VerificationResult(False, f"Destination size mismatch ({dest_size} vs {expected_size})")
        return VerificationResult(True, "Copy verified")

    @staticmethod
    def verify_delete(target: Path) -> VerificationResult:
        return VerificationResult(not target.exists(), f"{target} removed")

    @staticmethod
    def verify_create_dir(target: Path) -> VerificationResult:
        return VerificationResult(target.exists() and target.is_dir(), f"{target} created")
