"""
Response formatter to keep user-facing output clean and verifiable.

Outputs clean, human-readable text - no JSON dumps, no code fences,
no technical artifacts. Clean UX is the goal.
"""

import os
import re
from typing import Iterable, Optional, TYPE_CHECKING

from leonard.tools.base import ToolResult

if TYPE_CHECKING:
    from leonard.context.entities import Entity
    from leonard.context.resolver import ResolvedReference


def _human_size(size_bytes: int) -> str:
    if size_bytes is None:
        return ""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / 1024 / 1024:.1f} MB"


def _short_path(path: str) -> str:
    """Shorten path for display by replacing home with ~."""
    home = os.path.expanduser("~")
    if path.startswith(home):
        return "~" + path[len(home):]
    return path


class ResponseFormatter:
    """Converts tool results and model text into UI-friendly strings."""

    MAX_LIST_ITEMS = 8
    MAX_READ_LINES = 60

    @staticmethod
    def format_tool_result(result: ToolResult) -> str:
        if not result:
            return "No tool result returned. Please retry."

        if ResponseFormatter._verification_failed(result):
            details = result.verification_details or (
                result.verification.details if result.verification else None
            )
            return ResponseFormatter._format_error(result, override_summary=details)

        if result.status == "error":
            return ResponseFormatter._format_error(result)

        return ResponseFormatter._format_success(result)

    @staticmethod
    def sanitize_text(text: str) -> str:
        """
        Remove JSON/tool blocks and triple quotes from model output.
        Keeps plain text only.
        """
        cleaned = re.sub(r"```(?:json|tool)?\s*.*?```", "", text, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r"\{\s*\"tool\"[^}]*\}", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r"`{3,}", "", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    # ─────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _verification_failed(result: ToolResult) -> bool:
        if result.verification_passed is False:
            return True
        if result.verification and not result.verification.passed:
            return True
        # Enforce verification for mutations
        mutation_actions = {"write", "append", "move", "copy", "delete", "create", "organize"}
        if result.action in mutation_actions and result.verification_passed is None and not result.verification:
            return True
        return False

    @staticmethod
    def _format_with_summary(summary: str, lines: Iterable[str]) -> str:
        detail_lines = [line for line in lines if line]
        if detail_lines:
            return "\n".join([summary] + detail_lines)
        return summary

    @staticmethod
    def _format_success(result: ToolResult) -> str:
        """
        Format a successful tool result.
        """
        summary = result.display_summary_user or result.message_user or "Action completed."
        lines: list[str] = []

        if result.action == "list" and isinstance(result.output, dict):
            summary, lines = ResponseFormatter._render_list_output(result.output)
        elif result.action == "read" and isinstance(result.output, dict):
            summary, lines = ResponseFormatter._render_read_output(result.output)
        elif result.action == "search" and isinstance(result.output, dict):
            summary, lines = ResponseFormatter._render_search_output(result.output)
        elif result.action in {"move", "copy", "delete", "write", "append", "create", "organize"}:
            summary = ResponseFormatter._render_mutation_summary(result)

        return ResponseFormatter._format_with_summary(summary, lines)

    @staticmethod
    def _format_error(result: ToolResult, override_summary: str | None = None) -> str:
        summary = override_summary or result.display_summary_user or result.message_user or result.error or "Operation failed."
        details: list[str] = []
        if result.error and result.error != summary:
            details.append(result.error)
        if result.verification_details and result.verification_details != summary:
            details.append(result.verification_details)
        elif result.verification and result.verification.details != summary:
            details.append(result.verification.details)
        return ResponseFormatter._format_with_summary(summary, details)

    @staticmethod
    def _render_list_output(output: dict) -> tuple[str, list[str]]:
        path = output.get("path")
        items = output.get("items", [])
        short_path = _short_path(path) if path else "that folder"
        summary = f"Found {len(items)} item(s) in {short_path}:"
        lines: list[str] = []
        for item in items[: ResponseFormatter.MAX_LIST_ITEMS]:
            size = _human_size(item.get("size_bytes"))
            size_display = f", {size}" if size else ""
            item_type = item.get("type") or ("dir" if item.get("is_dir") else "file")
            lines.append(f"{len(lines) + 1}) {item.get('name')} ({item_type}{size_display})")
        if len(items) > ResponseFormatter.MAX_LIST_ITEMS:
            lines.append(f"...and {len(items) - ResponseFormatter.MAX_LIST_ITEMS} more")
        return summary, lines

    @staticmethod
    def _render_read_output(output: dict) -> tuple[str, list[str]]:
        path = output.get("path", "")
        short_path = _short_path(path) if path else "that file"
        lines = output.get("lines") or []
        shown = lines[: ResponseFormatter.MAX_READ_LINES]
        summary = f"Here are the first {len(shown)} line(s) from {short_path}:"
        if len(lines) > ResponseFormatter.MAX_READ_LINES:
            shown = shown + ["... (truncated)"]
        return summary, shown

    @staticmethod
    def _render_search_output(output: dict) -> tuple[str, list[str]]:
        count = output.get("count", 0)
        matches = output.get("matches") or []
        summary = f"Found {count} match(es)."
        lines: list[str] = []
        for match in matches[: ResponseFormatter.MAX_LIST_ITEMS]:
            path = match.get("path") if isinstance(match, dict) else str(match)
            lines.append(f"{len(lines) + 1}) {_short_path(path)}")
        if output.get("truncated"):
            lines.append("...and more (truncated)")
        return summary, lines

    @staticmethod
    def _render_mutation_summary(result: ToolResult) -> str:
        action = result.action or ""
        if action == "delete" and isinstance(result.output, dict) and result.output.get("pattern"):
            return result.message_user or "Deleted matching files."
        before = result.before_paths[0] if result.before_paths else ""
        after = result.after_paths[0] if result.after_paths else ""
        before_name = os.path.basename(before) if before else ""
        after_name = os.path.basename(after) if after else ""
        before_dir = os.path.dirname(before) if before else ""
        after_dir = os.path.dirname(after) if after else ""
        before_dir_short = _short_path(before_dir) if before_dir else ""
        after_dir_short = _short_path(after_dir) if after_dir else ""

        if action == "move":
            if before_dir and after_dir and before_dir == after_dir:
                return f"Renamed '{before_name}' → '{after_name}' in {before_dir_short}."
            return f"Moved '{before_name}' to {after_dir_short}."
        if action == "copy":
            return f"Copied '{before_name}' to {after_dir_short}."
        if action == "delete":
            return f"Deleted '{before_name}'."
        if action in {"write", "append"}:
            return f"Wrote '{after_name}' in {after_dir_short}."
        if action == "create":
            return f"Created folder '{after_name}' in {after_dir_short}."
        if action == "organize":
            return result.display_summary_user or result.message_user or "Organized files."
        return result.message_user or "Action completed."

    # ─────────────────────────────────────────────────────────
    # Entity-aware formatting (chat-aware actions)
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def format_disambiguation(
        alternatives: list["Entity"],
        action: str = "operate on",
    ) -> str:
        """
        Format a disambiguation question for the user.

        Produces clean numbered options, not JSON.
        """
        if not alternatives:
            return "I couldn't find a matching file. Can you specify the path?"

        if len(alternatives) == 1:
            e = alternatives[0]
            path = _short_path(e.absolute_path)
            return f"Did you mean {e.display_name} ({path})? Reply yes or specify another file."

        lines = [f"I found {len(alternatives)} files. Which one do you want to {action}?"]
        for i, e in enumerate(alternatives[:5], 1):
            path = _short_path(e.absolute_path)
            lines.append(f"{i}) {e.display_name} ({path})")

        if len(alternatives) > 5:
            lines.append(f"...and {len(alternatives) - 5} more")

        lines.append("Reply with the number, or specify a path.")
        return "\n".join(lines)

    @staticmethod
    def format_confirmation_request(
        entity: "Entity",
        action: str,
        destination_path: Optional[str] = None,
    ) -> str:
        """
        Format a confirmation request for destructive actions.

        Clean, direct question - no JSON.
        """
        path = _short_path(entity.absolute_path)
        destination = _short_path(destination_path) if destination_path else None
        action_verb = {
            "delete": "Delete",
            "delete_file": "Delete",
            "move": "Move",
            "move_file": "Move",
            "overwrite": "Overwrite",
            "write_file": "Overwrite",
        }.get(action, action.capitalize())

        if destination:
            return f"{action_verb} {path} → {destination}? (yes/no)"
        return f"{action_verb} {path}? (yes/no)"

    @staticmethod
    def format_confirmation_request_for_path(
        path: str,
        action: str,
        destination_path: Optional[str] = None,
    ) -> str:
        """Format a confirmation request when no entity object is available."""
        short_path = _short_path(path)
        destination = _short_path(destination_path) if destination_path else None
        action_verb = {
            "delete": "Delete",
            "delete_file": "Delete",
            "delete_by_pattern": "Delete",
            "move": "Move",
            "move_file": "Move",
            "overwrite": "Overwrite",
            "write_file": "Overwrite",
        }.get(action, action.capitalize())

        if destination:
            return f"{action_verb} {short_path} → {destination}? (yes/no)"
        return f"{action_verb} {short_path}? (yes/no)"

    @staticmethod
    def format_action_complete(
        action: str,
        source_name: str,
        destination_name: Optional[str] = None,
        source_path: Optional[str] = None,
        destination_path: Optional[str] = None,
    ) -> str:
        """
        Format a successful action completion message.

        Clean, concise confirmation - no JSON, no technical artifacts.
        """
        src_display = _short_path(source_path) if source_path else source_name
        dst_display = _short_path(destination_path) if destination_path else destination_name

        if action in ("move", "move_file", "rename"):
            if destination_name:
                return f"Renamed {source_name} → {destination_name}"
            return f"Moved {src_display}"

        elif action in ("delete", "delete_file"):
            return f"Deleted {source_name}"

        elif action in ("copy", "copy_file"):
            return f"Copied {source_name} → {dst_display}"

        elif action in ("create", "write", "write_file"):
            return f"Created {source_name}"

        elif action in ("read", "read_file"):
            return f"Read {source_name}"

        elif action == "list":
            return f"Listed {source_name}"

        elif action in ("create_directory", "mkdir"):
            return f"Created folder {source_name}"

        else:
            return f"{action.capitalize()} completed on {source_name}"

    @staticmethod
    def format_entity_resolved(
        entity: "Entity",
        reason: str,
    ) -> str:
        """Format message when entity was resolved from context."""
        path = _short_path(entity.absolute_path)
        if "pronoun" in reason.lower():
            return f"(Resolved 'it' to {entity.display_name})"
        elif "ordinal" in reason.lower():
            return f"(Selected {entity.display_name} from list)"
        elif "recent" in reason.lower():
            return f"(Using recently accessed {entity.display_name})"
        return ""

    @staticmethod
    def format_no_match() -> str:
        """Format message when no entity could be resolved."""
        return "I'm not sure which file you mean. Can you specify the path or name?"

    @staticmethod
    def format_selection_prompt(
        entities: list["Entity"],
        action: str = "select",
    ) -> str:
        """
        Format a numbered selection list.

        For list/search results that can be referenced by ordinal.
        """
        lines = []
        for i, e in enumerate(entities[:10], 1):
            path = _short_path(e.absolute_path)
            kind = "📁" if e.kind.value == "folder" else "📄"
            lines.append(f"  {i}. {kind} {e.display_name}")

        if len(entities) > 10:
            lines.append(f"  ...and {len(entities) - 10} more")

        return "\n".join(lines)

    @staticmethod
    def format_tool_unavailable(tool_name: str) -> str:
        """Format a message when a tool is unavailable or disabled."""
        if tool_name:
            return f"That action isn't available right now. ({tool_name})"
        return "That action isn't available right now."
