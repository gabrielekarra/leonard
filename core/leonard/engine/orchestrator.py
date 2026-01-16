"""
Main orchestrator that ties everything together.
The orchestrator handles ALL tool logic - the model never generates tool calls.

CHAT-AWARE ACTIONS:
- Tracks files/folders mentioned during conversation as entities
- Resolves references like "it", "that file", "the second one"
- Requires confirmation for destructive actions on pronoun-resolved targets
- Verifies all filesystem mutations before reporting success
"""

import os
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import AsyncGenerator, Optional, Callable, Awaitable

from leonard.context import (
    ConversationContext,
    Entity,
    EntityStore,
)
from leonard.engine.router import Router, RoutingDecision
from leonard.models.downloader import ModelDownloader
from leonard.models.registry import ModelRegistry
from leonard.runtime.process_manager import ProcessManager
from leonard.tools.executor import ToolExecutor
from leonard.utils.logging import logger
from leonard.utils.response_formatter import ResponseFormatter
from leonard.utils.action_guard import ActionGuard


class PlanStatus(str, Enum):
    """Planner status for tool execution."""
    READY = "ready"
    NEEDS_DISAMBIGUATION = "needs_disambiguation"
    NEEDS_CLARIFICATION = "needs_clarification"
    NO_ACTION = "no_action"


@dataclass
class PlannedAction:
    """Planner output for a tool action."""
    status: PlanStatus
    tool_name: Optional[str] = None
    params: dict = field(default_factory=dict)
    resolved_entity: Optional[Entity] = None
    alternatives: list[Entity] = field(default_factory=list)
    explicit_path: bool = False
    selection_resolved: bool = False
    destination_path: Optional[str] = None
    reason: Optional[str] = None


class LeonardOrchestrator:
    """
    The brain of Leonard.

    ARCHITECTURE:
    - Orchestrator detects ALL file operations via pattern matching
    - Orchestrator executes tools directly
    - Model NEVER sees tool syntax
    - Model only receives tool results and describes them naturally
    """

    USER_HOME = os.path.expanduser("~")
    USER_NAME = os.path.basename(USER_HOME)

    # Folder name mappings (lowercase)
    FOLDER_MAP = {
        "downloads": "Downloads",
        "download": "Downloads",
        "scaricati": "Downloads",
        "documents": "Documents",
        "docs": "Documents",
        "documenti": "Documents",
        "desktop": "Desktop",
        "scrivania": "Desktop",
        "images": "Images",
        "immagini": "Images",
        "home": "",
    }

    # System prompt - STRICT: model must NEVER claim file actions happened
    SYSTEM_PROMPT = f"""You are Leonard, a friendly AI assistant running locally on the user's Mac.

CONTEXT:
- User: {USER_NAME}
- Desktop (Scrivania): {USER_HOME}/Desktop
- Downloads (Scaricati): {USER_HOME}/Downloads
- Documents (Documenti): {USER_HOME}/Documents

CRITICAL RULES (MUST FOLLOW):
1. You do NOT directly delete, rename, move, create, or modify files.
2. File operations are handled by a separate tool system that you can request.
3. NEVER say "I deleted", "I renamed", "Done", "Completed", "Success" for file actions.
4. NEVER use past tense for file operations (deleted, renamed, moved, created).
5. NEVER use checkmarks (✓ ✔ ✅) to indicate file operations completed.
6. If asked to do a file operation, ask for needed details (path, destination, which file) or say you'll run it.
7. Only describe file operation results if they were provided by the system after tool execution.

WHAT YOU CAN DO:
- Answer questions about files listed in conversation history
- Help the user understand what files they have
- Explain what operations WOULD do (without claiming they happened)
- Ask for clarification about which file the user means

RESPONSE STYLE:
- Keep replies concise and friendly
- No JSON, no triple quotes, no code fences
- Plain natural language only
"""

    SYSTEM_PROMPT_NO_TOOLS = """You are Leonard, a friendly AI assistant.
You currently don't have file system access. Just chat normally.
NEVER claim you can delete, rename, move, or create files - you cannot."""

    def __init__(
        self,
        tools_enabled: bool = True,
        rag_enabled: bool = True,
        confirmation_callback: Optional[Callable[[str, dict], Awaitable[bool]]] = None,
        conversation_id: Optional[str] = None,
    ):
        self.process_manager = ProcessManager()
        self.registry = ModelRegistry()
        self.downloader = ModelDownloader()
        self.router = Router(self.process_manager, self.registry)

        self.tools_enabled = tools_enabled
        self.tool_executor = ToolExecutor(confirmation_callback=confirmation_callback) if tools_enabled else None

        self.rag_enabled = rag_enabled
        self._memory_manager = None

        self.conversation: list[dict] = []
        self._last_routing: Optional[RoutingDecision] = None
        self._initialized = False
        self._last_tool_result: Optional[dict] = None

        # Legacy context (kept for backwards compatibility)
        self._pending_action: Optional[dict] = None  # For follow-up confirmations
        self._last_directory_context: Optional[dict] = None  # {'path': str, 'items': list[str]}

        # Chat-aware entity context
        self._entity_store = EntityStore()
        self._conversation_id = conversation_id or str(uuid.uuid4())
        self._context = ConversationContext(
            conversation_id=self._conversation_id,
            store=self._entity_store,
        )

    @property
    def conversation_id(self) -> str:
        """Get the current conversation ID."""
        return self._conversation_id

    def set_conversation_id(self, conversation_id: str) -> None:
        """Set a new conversation ID (creates new context)."""
        self._conversation_id = conversation_id
        self._context = ConversationContext(
            conversation_id=conversation_id,
            store=self._entity_store,
        )

    async def initialize(self):
        """Initialize Leonard."""
        if self._initialized:
            return

        router_model = self.registry.get_router()

        if not router_model.is_downloaded or not router_model.local_path:
            existing_path = self.downloader.get_model_path(
                router_model.repo_id, router_model.filename
            )
            if existing_path:
                logger.info(f"Found model at {existing_path}")
                self.registry.update_download_status(
                    router_model.id, is_downloaded=True, local_path=str(existing_path)
                )
            else:
                logger.info("Model not found, downloading...")
                path = await self.downloader.download(
                    repo_id=router_model.repo_id, filename=router_model.filename
                )
                self.registry.update_download_status(
                    router_model.id, is_downloaded=True, local_path=str(path)
                )

        await self.router.ensure_router_ready()

        if self.rag_enabled:
            try:
                from leonard.memory import MemoryManager
                self._memory_manager = MemoryManager()
                await self._memory_manager.initialize()
            except Exception as e:
                logger.warning(f"RAG init failed: {e}")
                self._memory_manager = None

        self._initialized = True
        logger.info("Leonard initialized")

    async def chat(self, message: str) -> str:
        """Main chat entry point with chat-aware entity resolution."""
        if not self._initialized:
            await self.initialize()

        self._last_tool_result = None
        self._context.next_turn()
        self.conversation.append({"role": "user", "content": message})

        # Handle confirmation/cancellation for pending actions
        if self.tools_enabled and self.tool_executor:
            pending_response = await self._handle_pending_action(message)
            if pending_response:
                return pending_response

            # Detect tool actions before routing to a model
            planned = self._detect_tool_action_with_context(message)
            if planned:
                if planned.status == PlanStatus.NEEDS_CLARIFICATION:
                    response = planned.reason or (
                        "I need the exact source and destination (or new name) to rename/move files, "
                        "or a concrete path to run the action. Please provide the full paths."
                    )
                    self.conversation.append({"role": "assistant", "content": response})
                    return response

                if planned.status == PlanStatus.NEEDS_DISAMBIGUATION:
                    self._context.set_pending_action(
                        tool_name=planned.tool_name or "",
                        params=planned.params,
                        entity=None,
                        reason=planned.reason or "Disambiguation required",
                    )
                    response = ResponseFormatter.format_disambiguation(
                        planned.alternatives,
                        action=self._extract_action_verb(message),
                    )
                    self.conversation.append({"role": "assistant", "content": response})
                    return response

                if planned.status == PlanStatus.READY and planned.tool_name:
                    if not self._tool_available(planned.tool_name):
                        response = ResponseFormatter.format_tool_unavailable(planned.tool_name)
                        self.conversation.append({"role": "assistant", "content": response})
                        return response

                    if self._needs_confirmation_for_action(planned):
                        return self._request_confirmation(planned)

                    logger.info(f"Executing tool: {planned.tool_name} with {planned.params}")

                    result = await self.tool_executor.execute(planned.tool_name, planned.params)
                    self._last_tool_result = result.to_dict() if result else None
                    self._update_context_from_result(result)

                    # Track entities from result
                    if result and result.success:
                        self._context.track_from_tool_result(result)

                    formatted = ResponseFormatter.format_tool_result(result)
                    self.conversation.append({"role": "assistant", "content": formatted})
                    return formatted

            if self._looks_like_filesystem_intent(message):
                # Try to resolve reference first
                resolution = self._context.resolve(message)
                if resolution.is_ambiguous:
                    action = self._extract_action_verb(message)
                    params = {"path": ""}
                    if action in ("move", "rename"):
                        dest = self._extract_destination_from_message(
                            message,
                            base_dir=self._get_context_folder() or self.USER_HOME,
                            source_name=None,
                        )
                        params = {"source": "", "destination": dest or ""}
                    self._context.set_pending_action(
                        tool_name=self._map_action_to_tool(action),
                        params=params,
                        entity=None,
                        reason=resolution.reason,
                    )
                    response = ResponseFormatter.format_disambiguation(
                        resolution.alternatives,
                        action=self._extract_action_verb(message),
                    )
                    self.conversation.append({"role": "assistant", "content": response})
                    return response

                if resolution.entity:
                    action = self._extract_action_verb(message)
                    if action == "delete":
                        planned = PlannedAction(
                            status=PlanStatus.READY,
                            tool_name="delete_file",
                            params={"path": resolution.entity.absolute_path},
                            resolved_entity=resolution.entity,
                        )
                    elif action == "read":
                        planned = PlannedAction(
                            status=PlanStatus.READY,
                            tool_name="read_file",
                            params={"path": resolution.entity.absolute_path},
                            resolved_entity=resolution.entity,
                        )
                    elif action in ("move", "rename"):
                        dest = self._extract_destination_from_message(
                            message,
                            base_dir=os.path.dirname(resolution.entity.absolute_path),
                            source_name=resolution.entity.display_name,
                        )
                        if dest:
                            planned = PlannedAction(
                                status=PlanStatus.READY,
                                tool_name="move_file",
                                params={
                                    "source": resolution.entity.absolute_path,
                                    "destination": dest,
                                },
                                resolved_entity=resolution.entity,
                                destination_path=dest,
                            )
                        else:
                            response = (
                                "I need the destination path or new name to move/rename it. "
                                "Please provide the destination."
                            )
                            self.conversation.append({"role": "assistant", "content": response})
                            return response
                    else:
                        planned = None

                    if planned and planned.tool_name:
                        if not self._tool_available(planned.tool_name):
                            response = ResponseFormatter.format_tool_unavailable(planned.tool_name)
                            self.conversation.append({"role": "assistant", "content": response})
                            return response
                        if self._needs_confirmation_for_action(planned):
                            return self._request_confirmation(planned)
                        result = await self.tool_executor.execute(planned.tool_name, planned.params)
                        self._last_tool_result = result.to_dict() if result else None
                        self._update_context_from_result(result)
                        if result and result.success:
                            self._context.track_from_tool_result(result)
                        formatted = ResponseFormatter.format_tool_result(result)
                        self.conversation.append({"role": "assistant", "content": formatted})
                        return formatted

                prompt = (
                    "I need the exact source and destination (or new name) to rename/move files, "
                    "or a concrete path to run the action. Please provide the full paths."
                )
                self.conversation.append({"role": "assistant", "content": prompt})
                return prompt

        # Route to model when no tool is executed
        # IMPORTANT: Model response must NOT claim file actions happened
        decision = await self.router.route(message)
        self._last_routing = decision
        await self._ensure_model_ready(decision.model_id)

        messages = self._build_messages()

        response = await self.process_manager.chat(
            model_id=decision.model_id,
            messages=messages,
        )

        response = ResponseFormatter.sanitize_text(self._clean_response(response))

        # CRITICAL: Validate model response - block hallucinated action claims
        # No tool was executed this turn, so model must NOT claim success
        response, was_blocked = ActionGuard.validate_model_response(
            response, tool_was_executed=False
        )
        if was_blocked:
            logger.warning(f"Blocked hallucinated action claim from model")

        self.conversation.append({"role": "assistant", "content": response})
        return response

    async def _handle_pending_action(self, message: str) -> Optional[str]:
        """Handle confirmation or cancellation of pending action."""
        pending = self._context.get_pending_action()
        if not pending:
            # Check legacy pending action
            if self._pending_action:
                msg = message.lower().strip()
                if msg in ("yes", "sì", "si", "ok", "sure", "do it", "proceed", "vai", "fallo"):
                    action = self._pending_action
                    self._pending_action = None
                    if not self._tool_available(action["tool"]):
                        response = ResponseFormatter.format_tool_unavailable(action["tool"])
                        self.conversation.append({"role": "assistant", "content": response})
                        return response
                    result = await self.tool_executor.execute(action["tool"], action["params"])
                    self._last_tool_result = result.to_dict() if result else None
                    self._update_context_from_result(result)
                    if result and result.success:
                        self._context.track_from_tool_result(result)
                    formatted = ResponseFormatter.format_tool_result(result)
                    self.conversation.append({"role": "assistant", "content": formatted})
                    return formatted
            return None

        if self._context.is_confirmation(message):
            self._context.clear_pending_action()
            if not self._tool_available(pending.tool_name):
                response = ResponseFormatter.format_tool_unavailable(pending.tool_name)
                self.conversation.append({"role": "assistant", "content": response})
                return response
            result = await self.tool_executor.execute(pending.tool_name, pending.params)
            self._last_tool_result = result.to_dict() if result else None
            self._update_context_from_result(result)
            if result and result.success:
                self._context.track_from_tool_result(result)
            formatted = ResponseFormatter.format_tool_result(result)
            self.conversation.append({"role": "assistant", "content": formatted})
            return formatted

        if self._context.is_cancellation(message):
            self._context.clear_pending_action()
            response = "Action cancelled."
            self.conversation.append({"role": "assistant", "content": response})
            return response

        # Check for ordinal selection (e.g., "2" or "the second one")
        ordinal_match = self._parse_ordinal_selection(message)
        if ordinal_match is not None:
            selection_items = self._context.get_selection_items()
            if 0 <= ordinal_match < len(selection_items):
                selected = selection_items[ordinal_match]
                # Update params with selected entity's path
                params = dict(pending.params)
                if "path" in params:
                    params["path"] = selected.absolute_path
                elif "source" in params:
                    params["source"] = selected.absolute_path

                if pending.tool_name == "move_file" and not params.get("destination"):
                    response = (
                        "I need the destination path or new name to move/rename it. "
                        "Please provide the destination."
                    )
                    self.conversation.append({"role": "assistant", "content": response})
                    return response

                self._context.clear_pending_action()
                if not self._tool_available(pending.tool_name):
                    response = ResponseFormatter.format_tool_unavailable(pending.tool_name)
                    self.conversation.append({"role": "assistant", "content": response})
                    return response
                result = await self.tool_executor.execute(pending.tool_name, params)
                self._last_tool_result = result.to_dict() if result else None
                self._update_context_from_result(result)
                if result and result.success:
                    self._context.track_from_tool_result(result)
                formatted = ResponseFormatter.format_tool_result(result)
                self.conversation.append({"role": "assistant", "content": formatted})
                return formatted

        return None

    def _parse_ordinal_selection(self, message: str) -> Optional[int]:
        """Parse ordinal selection from message, returning 0-based index."""
        msg = message.strip().lower()

        # Direct number
        if msg.isdigit():
            return int(msg) - 1

        # Ordinal words
        ordinals = {
            "first": 0, "1st": 0, "primo": 0,
            "second": 1, "2nd": 1, "secondo": 1,
            "third": 2, "3rd": 2, "terzo": 2,
            "fourth": 3, "4th": 3, "quarto": 3,
            "fifth": 4, "5th": 4, "quinto": 4,
            "last": -1, "ultimo": -1,
        }

        for word, idx in ordinals.items():
            if word in msg:
                return idx

        return None

    def _needs_confirmation_for_action(self, planned: PlannedAction) -> bool:
        """Check if action needs confirmation based on resolution confidence."""
        destructive_tools = {"delete_file", "delete_by_pattern", "move_file"}

        if planned.tool_name not in destructive_tools:
            return False

        if planned.tool_name == "delete_by_pattern":
            return True

        # High-confidence targets: explicit paths or user selection just now.
        if planned.explicit_path or planned.selection_resolved:
            return False

        # Everything else for destructive ops requires confirmation.
        return True

    def _request_confirmation(self, planned: PlannedAction) -> str:
        """Request confirmation for a destructive action."""
        self._context.set_pending_action(
            tool_name=planned.tool_name or "",
            params=planned.params,
            entity=planned.resolved_entity,
            reason=f"Destructive action on resolved reference",
        )

        if planned.resolved_entity:
            response = ResponseFormatter.format_confirmation_request(
                planned.resolved_entity,
                planned.tool_name or "",
                destination_path=planned.destination_path,
            )
        else:
            if planned.tool_name == "delete_by_pattern":
                directory = planned.params.get("directory") or ""
                pattern = planned.params.get("pattern") or ""
                path = f"{directory}/{pattern}" if pattern else directory
            else:
                path = planned.params.get("path") or planned.params.get("source") or planned.params.get("directory") or ""
            response = ResponseFormatter.format_confirmation_request_for_path(
                path,
                planned.tool_name or "",
                destination_path=planned.destination_path or planned.params.get("destination"),
            )
        self.conversation.append({"role": "assistant", "content": response})
        return response

    def _extract_action_verb(self, message: str) -> str:
        """Extract action verb from message for disambiguation prompt."""
        msg = message.lower()
        if "delete" in msg or "elimina" in msg or "rimuovi" in msg:
            return "delete"
        if "rename" in msg or "rinomina" in msg:
            return "rename"
        if "move" in msg or "sposta" in msg:
            return "move"
        if "read" in msg or "leggi" in msg or "open" in msg or "apri" in msg:
            return "read"
        return "operate on"

    def _map_action_to_tool(self, action: str) -> str:
        """Map a user action verb to a tool name."""
        mapping = {
            "delete": "delete_file",
            "rename": "move_file",
            "move": "move_file",
            "read": "read_file",
            "open": "read_file",
            "list": "list_directory",
            "organize": "organize_files",
        }
        return mapping.get(action, action)

    def _tool_available(self, tool_name: str) -> bool:
        """Check if a tool is available and enabled."""
        if not tool_name or not self.tools_enabled or not self.tool_executor:
            return False
        tool = self.tool_executor.registry.get(tool_name)
        return bool(tool and tool.enabled)

    def _tool_icon(self, category: str) -> str:
        """Map tool categories to UI icons."""
        return {
            "filesystem": "folder",
            "shell": "terminal",
            "web": "globe",
            "system": "gear",
        }.get(category, "tool")

    async def chat_stream(self, message: str) -> AsyncGenerator[str, None]:
        """Streaming chat with chat-aware entity resolution."""
        if not self._initialized:
            await self.initialize()

        self._last_tool_result = None
        self._context.next_turn()
        self.conversation.append({"role": "user", "content": message})

        if self.tools_enabled and self.tool_executor:
            # Handle pending confirmations
            pending_response = await self._handle_pending_action(message)
            if pending_response:
                yield pending_response
                return

            planned = self._detect_tool_action_with_context(message)
            if planned:
                if planned.status == PlanStatus.NEEDS_CLARIFICATION:
                    response = planned.reason or (
                        "I need the exact source and destination (or new name) to rename/move files, "
                        "or a concrete path to run the action. Please provide the full paths."
                    )
                    self.conversation.append({"role": "assistant", "content": response})
                    yield response
                    return

                if planned.status == PlanStatus.NEEDS_DISAMBIGUATION:
                    self._context.set_pending_action(
                        tool_name=planned.tool_name or "",
                        params=planned.params,
                        entity=None,
                        reason=planned.reason or "Disambiguation required",
                    )
                    response = ResponseFormatter.format_disambiguation(
                        planned.alternatives,
                        action=self._extract_action_verb(message),
                    )
                    self.conversation.append({"role": "assistant", "content": response})
                    yield response
                    return

                if planned.status == PlanStatus.READY and planned.tool_name:
                    if not self._tool_available(planned.tool_name):
                        response = ResponseFormatter.format_tool_unavailable(planned.tool_name)
                        self.conversation.append({"role": "assistant", "content": response})
                        yield response
                        return

                    if self._needs_confirmation_for_action(planned):
                        response = self._request_confirmation(planned)
                        yield response
                        return

                    result = await self.tool_executor.execute(planned.tool_name, planned.params)
                    self._last_tool_result = result.to_dict() if result else None
                    self._update_context_from_result(result)
                    if result and result.success:
                        self._context.track_from_tool_result(result)
                    formatted = ResponseFormatter.format_tool_result(result)
                    self.conversation.append({"role": "assistant", "content": formatted})
                    yield formatted
                    return

            if self._looks_like_filesystem_intent(message):
                resolution = self._context.resolve(message)
                if resolution.is_ambiguous:
                    action = self._extract_action_verb(message)
                    params = {"path": ""}
                    if action in ("move", "rename"):
                        dest = self._extract_destination_from_message(
                            message,
                            base_dir=self._get_context_folder() or self.USER_HOME,
                            source_name=None,
                        )
                        params = {"source": "", "destination": dest or ""}
                    self._context.set_pending_action(
                        tool_name=self._map_action_to_tool(action),
                        params=params,
                        entity=None,
                        reason=resolution.reason,
                    )
                    response = ResponseFormatter.format_disambiguation(
                        resolution.alternatives,
                        action=action,
                    )
                    self.conversation.append({"role": "assistant", "content": response})
                    yield response
                    return

                if resolution.entity:
                    action = self._extract_action_verb(message)
                    if action == "delete":
                        planned = PlannedAction(
                            status=PlanStatus.READY,
                            tool_name="delete_file",
                            params={"path": resolution.entity.absolute_path},
                            resolved_entity=resolution.entity,
                        )
                    elif action == "read":
                        planned = PlannedAction(
                            status=PlanStatus.READY,
                            tool_name="read_file",
                            params={"path": resolution.entity.absolute_path},
                            resolved_entity=resolution.entity,
                        )
                    elif action in ("move", "rename"):
                        dest = self._extract_destination_from_message(
                            message,
                            base_dir=os.path.dirname(resolution.entity.absolute_path),
                            source_name=resolution.entity.display_name,
                        )
                        if dest:
                            planned = PlannedAction(
                                status=PlanStatus.READY,
                                tool_name="move_file",
                                params={
                                    "source": resolution.entity.absolute_path,
                                    "destination": dest,
                                },
                                resolved_entity=resolution.entity,
                                destination_path=dest,
                            )
                        else:
                            response = (
                                "I need the destination path or new name to move/rename it. "
                                "Please provide the destination."
                            )
                            self.conversation.append({"role": "assistant", "content": response})
                            yield response
                            return
                    else:
                        planned = None

                    if planned and planned.tool_name:
                        if not self._tool_available(planned.tool_name):
                            response = ResponseFormatter.format_tool_unavailable(planned.tool_name)
                            self.conversation.append({"role": "assistant", "content": response})
                            yield response
                            return
                        if self._needs_confirmation_for_action(planned):
                            response = self._request_confirmation(planned)
                            yield response
                            return
                        result = await self.tool_executor.execute(planned.tool_name, planned.params)
                        self._last_tool_result = result.to_dict() if result else None
                        self._update_context_from_result(result)
                        if result and result.success:
                            self._context.track_from_tool_result(result)
                        formatted = ResponseFormatter.format_tool_result(result)
                        self.conversation.append({"role": "assistant", "content": formatted})
                        yield formatted
                        return

                prompt = (
                    "I need the exact source and destination (or new name) to rename/move files, "
                    "or a concrete path to run the action. Please provide the full paths."
                )
                self.conversation.append({"role": "assistant", "content": prompt})
                yield prompt
                return

        # Route to model when no tool is executed
        # IMPORTANT: Model response must NOT claim file actions happened
        decision = await self.router.route(message)
        self._last_routing = decision
        await self._ensure_model_ready(decision.model_id)

        messages = self._build_messages()

        full_response = ""
        async for chunk in self.process_manager.chat_stream(
            model_id=decision.model_id,
            messages=messages,
        ):
            # Filter out any tool syntax in real-time
            clean_chunk = self._clean_chunk(chunk)
            if clean_chunk:
                full_response += clean_chunk

        full_response = ResponseFormatter.sanitize_text(self._clean_response(full_response))

        # CRITICAL: Validate model response - block hallucinated action claims
        # No tool was executed this turn, so model must NOT claim success
        validated_response, was_blocked = ActionGuard.validate_model_response(
            full_response, tool_was_executed=False
        )
        if was_blocked:
            logger.warning(f"Blocked hallucinated action claim from model (stream)")
            full_response = validated_response

        self.conversation.append({"role": "assistant", "content": full_response})
        yield full_response

    def _build_messages(self) -> list[dict]:
        """Build message list for model - NO tool syntax."""
        system_prompt = self.SYSTEM_PROMPT if self.tools_enabled else self.SYSTEM_PROMPT_NO_TOOLS
        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history (limited)
        for msg in self.conversation[-10:]:
            messages.append(msg)

        return messages

    def _update_context_from_result(self, result):
        """Capture directory context from tool results for follow-up actions."""
        if not result:
            return
        if getattr(result, "action", None) == "list" and isinstance(result.output, dict):
            path = result.output.get("path")
            items_raw = result.output.get("items", [])
            names = [i.get("name") for i in items_raw if isinstance(i, dict) and i.get("name")]
            if path:
                self._last_directory_context = {"path": path, "items": names}

    def _detect_tool_action_with_context(
        self, message: str
    ) -> Optional[PlannedAction]:
        """
        Detect tool action with chat-aware entity resolution.

        Returns (tool_name, params, resolved_entity) or None.
        The resolved_entity is set when a pronoun/reference was resolved.
        """
        msg = message.lower().strip()

        # Try to detect action first using legacy method
        legacy_action = self._detect_tool_action(message)

        # Check for pronoun references that need resolution
        pronoun_patterns = [
            r"\b(delete|rename|move|open|read)\s+(it|that|this)\b",
            r"\b(delete|elimina|rimuovi)\s+(it|that|this|the file|il file|quello)\b",
            r"\b(rename|rinomina)\s+(it|that|this)\s+to\b",
            r"\b(open|apri|read|leggi)\s+(it|that|this|the file)\b",
        ]

        needs_resolution = any(re.search(p, msg) for p in pronoun_patterns)

        if needs_resolution:
            # Determine action type for resolution
            if self._matches_delete(msg):
                action = "delete_file"
                resolution = self._context.resolve_for_action(message, action)

                if resolution.entity:
                    return PlannedAction(
                        status=PlanStatus.READY,
                        tool_name="delete_file",
                        params={"path": resolution.entity.absolute_path},
                        resolved_entity=resolution.entity,
                        alternatives=resolution.alternatives,
                    )
                if resolution.is_ambiguous:
                    return PlannedAction(
                        status=PlanStatus.NEEDS_DISAMBIGUATION,
                        tool_name="delete_file",
                        params={"path": ""},
                        alternatives=resolution.alternatives,
                        reason=resolution.reason,
                    )

            elif self._matches_read(msg):
                action = "read_file"
                resolution = self._context.resolve_for_action(message, action)

                if resolution.entity:
                    return PlannedAction(
                        status=PlanStatus.READY,
                        tool_name="read_file",
                        params={"path": resolution.entity.absolute_path},
                        resolved_entity=resolution.entity,
                        alternatives=resolution.alternatives,
                    )
                if resolution.is_ambiguous:
                    return PlannedAction(
                        status=PlanStatus.NEEDS_DISAMBIGUATION,
                        tool_name="read_file",
                        params={"path": ""},
                        alternatives=resolution.alternatives,
                        reason=resolution.reason,
                    )

            elif self._matches_move(msg):
                action = "move_file"
                resolution = self._context.resolve_for_action(message, action)

                if resolution.entity:
                    dest = self._extract_destination_from_message(
                        message,
                        base_dir=os.path.dirname(resolution.entity.absolute_path),
                        source_name=resolution.entity.display_name,
                    )
                    if dest:
                        return PlannedAction(
                            status=PlanStatus.READY,
                            tool_name="move_file",
                            params={
                                "source": resolution.entity.absolute_path,
                                "destination": dest,
                            },
                            resolved_entity=resolution.entity,
                            destination_path=dest,
                        )
                    return PlannedAction(
                        status=PlanStatus.NEEDS_CLARIFICATION,
                        tool_name="move_file",
                        params={"source": resolution.entity.absolute_path},
                        resolved_entity=resolution.entity,
                        reason=(
                            "I need the destination path or new name to move/rename it. "
                            "Please provide the destination."
                        ),
                    )
                if resolution.is_ambiguous:
                    dest = self._extract_destination_from_message(
                        message,
                        base_dir=self._get_context_folder() or self.USER_HOME,
                        source_name=None,
                    )
                    return PlannedAction(
                        status=PlanStatus.NEEDS_DISAMBIGUATION,
                        tool_name="move_file",
                        params={"source": "", "destination": dest or ""},
                        alternatives=resolution.alternatives,
                        reason=resolution.reason,
                    )

        # Check for ordinal references ("delete the first one", "open the second file")
        ordinal_patterns = [
            r"\b(delete|rename|move|open|read)\s+the\s+(first|second|third|fourth|fifth|last|1st|2nd|3rd|4th|5th)\b",
            r"\b(delete|elimina)\s+(il\s+)?(primo|secondo|terzo|quarto|quinto|ultimo)\b",
        ]

        for pattern in ordinal_patterns:
            match = re.search(pattern, msg)
            if match:
                # Get selection from context
                selection_items = self._context.get_selection_items()
                if selection_items:
                    ordinal_idx = self._parse_ordinal_selection(match.group(2) if match.lastindex >= 2 else match.group(0))
                    if ordinal_idx is not None:
                        # Handle negative index (last)
                        if ordinal_idx == -1:
                            ordinal_idx = len(selection_items) - 1

                        if 0 <= ordinal_idx < len(selection_items):
                            entity = selection_items[ordinal_idx]

                            if self._matches_delete(msg):
                                return PlannedAction(
                                    status=PlanStatus.READY,
                                    tool_name="delete_file",
                                    params={"path": entity.absolute_path},
                                    resolved_entity=entity,
                                    selection_resolved=True,
                                )
                            if self._matches_read(msg):
                                return PlannedAction(
                                    status=PlanStatus.READY,
                                    tool_name="read_file",
                                    params={"path": entity.absolute_path},
                                    resolved_entity=entity,
                                    selection_resolved=True,
                                )
                            if self._matches_move(msg):
                                dest = self._extract_destination_from_message(
                                    message,
                                    base_dir=os.path.dirname(entity.absolute_path),
                                    source_name=entity.display_name,
                                )
                                if dest:
                                    return PlannedAction(
                                        status=PlanStatus.READY,
                                        tool_name="move_file",
                                        params={
                                            "source": entity.absolute_path,
                                            "destination": dest,
                                        },
                                        resolved_entity=entity,
                                        selection_resolved=True,
                                        destination_path=dest,
                                    )
                                return PlannedAction(
                                    status=PlanStatus.NEEDS_CLARIFICATION,
                                    tool_name="move_file",
                                    params={"source": entity.absolute_path},
                                    resolved_entity=entity,
                                    selection_resolved=True,
                                    reason=(
                                        "I need the destination path or new name to move/rename it. "
                                        "Please provide the destination."
                                    ),
                                )

        # Fall back to legacy detection if no context resolution needed
        if legacy_action:
            tool_name, params, explicit_path = legacy_action
            return PlannedAction(
                status=PlanStatus.READY,
                tool_name=tool_name,
                params=params,
                explicit_path=explicit_path,
            )

        return None

    def _detect_tool_action(self, message: str) -> Optional[tuple[str, dict, bool]]:
        """
        Detect what tool action to take based on user message.
        This is the ONLY place tool decisions are made.
        """
        msg = message.lower().strip()
        explicit_path = self._message_has_explicit_path(message)

        # Handle confirmations for pending actions
        if msg in ("yes", "sì", "si", "ok", "sure", "do it", "proceed", "vai", "fallo"):
            if self._pending_action:
                action = self._pending_action
                self._pending_action = None
                return (action["tool"], action["params"], False)
            return None

        # Extract folder from message
        folder_path = self._extract_folder(message)

        # === DELETE OPERATIONS ===
        if self._matches_delete(msg):
            # Delete current context folder if explicitly requested without a name
            if self._last_directory_context and re.search(r"\bdelete (the )?folder\b", msg):
                return ("delete_file", {"path": self._last_directory_context["path"]}, explicit_path)

            # Try to delete a named file inside the current context
            context_filename = self._extract_filename_from_context(message)
            if context_filename:
                return ("delete_file", {"path": context_filename}, explicit_path)

            # Check for specific file path
            path = self._extract_path(message)
            if path:
                return ("delete_file", {"path": path}, True)

            # Check for folder name in message (e.g., "delete folder Documents")
            folder_to_delete = self._extract_folder_to_delete(message)
            if folder_to_delete:
                return ("delete_file", {"path": folder_to_delete}, explicit_path)

            # Check for file patterns
            if "screenshot" in msg:
                target = folder_path or f"{self.USER_HOME}/Desktop"
                return ("delete_by_pattern", {"directory": target, "pattern": "Screenshot*.png"}, explicit_path)

            if any(w in msg for w in ["image", "immagin", "photo", "foto", "picture"]):
                target = folder_path or f"{self.USER_HOME}/Desktop"
                return ("delete_by_pattern", {"directory": target, "pattern": "*.png,*.jpg,*.jpeg,*.gif"}, explicit_path)

            # Generic delete - need to list first
            if folder_path:
                return ("list_directory", {"path": folder_path}, explicit_path)

        # === LIST OPERATIONS ===
        if self._matches_list(msg):
            target = folder_path
            if not target and self._last_directory_context:
                target = self._last_directory_context.get("path")
            if not target:
                last_folder = self._context.get_last_active_folder()
                if last_folder:
                    target = last_folder.absolute_path
            if not target:
                target = f"{self.USER_HOME}/Desktop"
            return ("list_directory", {"path": target}, explicit_path)

        # === ORGANIZE OPERATIONS ===
        if self._matches_organize(msg):
            target = folder_path or f"{self.USER_HOME}/Desktop"
            return ("organize_files", {"directory": target}, explicit_path)

        # === CREATE FILE ===
        if self._matches_create_file(msg):
            filename = self._extract_filename(message)
            if filename:
                target = folder_path or f"{self.USER_HOME}/Desktop"
                filepath = os.path.join(target, filename)
                content = self._extract_content(message)
                return ("write_file", {"path": filepath, "content": content}, explicit_path)

        # === MOVE / RENAME ===
        if self._matches_move(msg):
            move_paths = self._extract_move_paths(message)
            if move_paths:
                return ("move_file", move_paths, explicit_path or self._message_has_explicit_path(move_paths.get("source", "")))

        # === CREATE FOLDER ===
        if self._matches_create_folder(msg):
            foldername = self._extract_foldername(message)
            if foldername:
                target = folder_path or f"{self.USER_HOME}/Desktop"
                folderpath = os.path.join(target, foldername)
                return ("create_directory", {"path": folderpath}, explicit_path)

        # === READ FILE ===
        if self._matches_read(msg):
            context_filename = self._extract_filename_from_context(message)
            if context_filename:
                return ("read_file", {"path": context_filename}, explicit_path)

            path = self._extract_path(message)
            if path:
                return ("read_file", {"path": path}, True)

        # === SYSTEM INFO ===
        if self._matches_system_info(msg):
            return ("get_system_info", {}, False)

        return None

    # === Pattern Matching Methods ===

    def _matches_delete(self, msg: str) -> bool:
        patterns = [
            r"\b(delete|elimina|rimuovi|remove|cancella)\b",
            r"\b(can you delete|puoi eliminare|puoi cancellare)\b",
        ]
        return any(re.search(p, msg) for p in patterns)

    def _matches_list(self, msg: str) -> bool:
        patterns = [
            r"\b(what|which|quali|che)\b.{0,20}\b(file|folder|cartell)",
            r"\b(list|show|elenc|mostra|dimmi)\b.{0,20}\b(file|folder|cartell|content)",
            r"\b(list\w*|show)\s+(them|it|those|these)\b",
            r"^(list\w*|show)$",
            r"\b(cosa c'è|what's in|whats in)\b",
            r"\b(tell me).{0,10}(file|folder|what)",
            r"^(in |on |e |and )?(the )?(my )?(desktop|scrivania|downloads?|scaricati|documents?|documenti)\??$",
        ]
        return any(re.search(p, msg) for p in patterns)

    def _matches_organize(self, msg: str) -> bool:
        patterns = [
            r"\b(organiz|organizza|riorganizza|reorganiz|ordina|riordina|tidy|sort)\b",
        ]
        return any(re.search(p, msg) for p in patterns)

    def _matches_move(self, msg: str) -> bool:
        patterns = [
            r"\b(move|sposta|rename|rinomina|spostare|renome)\b",
            r"\b(sposta|move)\s+.*\s+(?:to|in|into)\b",
        ]
        return any(re.search(p, msg) for p in patterns)

    def _matches_create_file(self, msg: str) -> bool:
        patterns = [
            r"\b(create|crea|nuovo|new|scrivi|write)\b.{0,20}\bfile\b",
        ]
        return any(re.search(p, msg) for p in patterns)

    def _matches_create_folder(self, msg: str) -> bool:
        patterns = [
            r"\b(create|crea|nuovo|new)\b.{0,20}\b(folder|cartella|directory)\b",
        ]
        return any(re.search(p, msg) for p in patterns)

    def _matches_read(self, msg: str) -> bool:
        patterns = [
            r"\b(read|leggi|open|apri|show|mostra)\b.{0,20}\bfile\b",
            r"\b(content|contenuto)\b.{0,10}\b(of|del|di)\b",
        ]
        return any(re.search(p, msg) for p in patterns)

    def _matches_system_info(self, msg: str) -> bool:
        patterns = [
            r"\b(system|sistema)\s+(info|informazion)",
            r"\b(how much|quanta)\s+(memory|ram|memoria)\b",
            r"\b(cpu|processor|disk)\s+(info|usage|space)\b",
        ]
        return any(re.search(p, msg) for p in patterns)

    def _looks_like_filesystem_intent(self, message: str) -> bool:
        """Detect if the user likely wanted a filesystem action but parameters were missing."""
        msg = message.lower().strip()
        return any(
            [
                self._matches_delete(msg),
                self._matches_list(msg),
                self._matches_organize(msg),
                self._matches_create_file(msg),
                self._matches_create_folder(msg),
                self._matches_read(msg),
                self._matches_move(msg),
            ]
        )

    def _resolve_context_subpath(self, folder_name: str) -> Optional[str]:
        """If the folder name exists in the last listed directory, return that path."""
        if not self._last_directory_context:
            return None
        base = self._last_directory_context.get("path")
        items = self._last_directory_context.get("items", [])
        for item in items:
            if item.lower() == folder_name.lower():
                return os.path.join(base, item)
        return None

    def _resolve_context_filename(self, name: str) -> Optional[str]:
        """Find a filename in the last directory context, matching full name or stem."""
        if not self._last_directory_context:
            return None
        items = self._last_directory_context.get("items", [])
        lowered = name.lower()
        # Exact match
        for item in items:
            if item.lower() == lowered:
                return item
        # Stem match if unique
        stem_matches = [item for item in items if os.path.splitext(item)[0].lower() == lowered]
        if len(stem_matches) == 1:
            return stem_matches[0]
        return None

    def _extract_move_paths(self, message: str) -> Optional[dict]:
        """
        Extract source/destination for move/rename.
        Supports:
        - move /path/a to /path/b
        - rename a.txt to b.txt (using context path if available)
        - rename the file "a.txt" into "b.txt"
        - move a.txt into folder (joins with context when possible)
        """
        # Absolute paths
        direct = re.search(r'\b(?:move|rename|sposta|rinomina)\s+["\']?(/[^"\s]+)["\']?\s+(?:to|into|in)\s+["\']?(/[^"\s]+)["\']?', message, re.IGNORECASE)
        if direct:
            return {"source": direct.group(1), "destination": direct.group(2)}

        # Absolute source with relative destination
        abs_src = re.search(
            r'\b(?:move|rename|sposta|rinomina)\s+["\']?(/[^"\s]+)["\']?\s+(?:to|into|in|as)\s+(?:just\s+|solo\s+)?["\']?([^\s"\']+)["\']?',
            message,
            re.IGNORECASE,
        )
        if abs_src:
            src_path = abs_src.group(1)
            dest = self._extract_destination_from_message(
                message,
                base_dir=os.path.dirname(src_path),
                source_name=os.path.basename(src_path),
            )
            if dest:
                return {"source": src_path, "destination": dest}

        base = self._last_directory_context.get("path") if self._last_directory_context else None

        # Flexible rename pattern - handles:
        # "rename X to Y", "rename the file X into Y", "rename X into just Y"
        # Allow optional "the file", "file", "il file" between verb and source
        # Allow optional "just", "solo" before destination
        rename = re.search(
            r'\b(?:rename|rinomina|move|sposta)\s+(?:the\s+)?(?:file\s+)?(?:il\s+)?["\']?([\w\.-]+\.[\w]+)["\']?\s+(?:to|as|into|in)\s+(?:just\s+)?(?:solo\s+)?["\']?([\w\.-]+\.[\w]+)["\']?',
            message,
            re.IGNORECASE,
        )
        if rename and base:
            src_name, dst_name = rename.group(1), rename.group(2)
            return {
                "source": os.path.join(base, src_name),
                "destination": os.path.join(base, dst_name),
            }

        # "rename X to Y" without explicit context but listed file is referenced
        if rename and not base and self._last_directory_context:
            src_name, dst_name = rename.group(1), rename.group(2)
            return {
                "source": os.path.join(self._last_directory_context["path"], src_name),
                "destination": os.path.join(self._last_directory_context["path"], dst_name),
            }

        # Move file into named folder within context
        move_into = re.search(
            r'\b(?:move|sposta)\s+(?:the\s+)?(?:file\s+)?["\']?([\w\.-]+\.[\w]+)["\']?\s+(?:to|into|in)\s+["\']?([\w\.-]+)["\']?',
            message,
            re.IGNORECASE,
        )
        if move_into and base:
            file_name, folder_name = move_into.group(1), move_into.group(2)
            src = os.path.join(base, file_name)
            folder_path = self._resolve_context_subpath(folder_name)
            if folder_path:
                return {"source": src, "destination": os.path.join(folder_path, file_name)}

        # Rename without explicit extension: "rename tessera-fif to tessera"
        # Also handles "rename the file X into just Y"
        rename_no_ext = re.search(
            r'\b(?:rename|rinomina|move|sposta)\s+(?:the\s+)?(?:file\s+)?(?:il\s+)?["\']?([\w\.-]+)["\']?\s+(?:to|as|into|in)\s+(?:just\s+)?(?:solo\s+)?["\']?([\w\.-]+)["\']?',
            message,
            re.IGNORECASE,
        )
        if rename_no_ext and base:
            src_token, dst_token = rename_no_ext.group(1), rename_no_ext.group(2)
            src_name = self._resolve_context_filename(src_token)
            if src_name:
                dst_name = dst_token
                # If destination has no extension, reuse source extension
                if "." not in os.path.basename(dst_name) and "." in os.path.basename(src_name):
                    dst_name = dst_name + os.path.splitext(src_name)[1]
                return {
                    "source": os.path.join(base, src_name),
                    "destination": os.path.join(base, dst_name),
                }

        # If only one file name is provided with "rename" and we have context, ask for destination
        single_name = re.search(r'\b(?:rename|rinomina|move|sposta)\s+["\']?([\w\.-]+)["\']?\b', message, re.IGNORECASE)
        if single_name and base:
            return None  # Will trigger prompt for destination upstream

        return None

    # === Extraction Methods ===

    def _extract_folder(self, message: str) -> Optional[str]:
        """Extract folder path from message."""
        msg = message.lower()

        # Context-aware resolution
        for keyword in self.FOLDER_MAP:
            if keyword in msg:
                resolved = self._resolve_context_subpath(keyword)
                if resolved:
                    return resolved
        # Check for explicit child name in current context (e.g., "inside documents folder")
        if "documents" in msg and self._last_directory_context:
            ctx_child = self._resolve_context_subpath("Documents")
            if ctx_child:
                return ctx_child

        # Check explicit path first
        path_match = re.search(r'["\']?(/[^\s"\']+)["\']?', message)
        if path_match:
            return path_match.group(1)

        # Check ~/ path
        home_match = re.search(r'["\']?(~/[^\s"\']+)["\']?', message)
        if home_match:
            return os.path.expanduser(home_match.group(1))

        # Check folder keywords
        for keyword, folder in self.FOLDER_MAP.items():
            if keyword in msg:
                resolved = self._resolve_context_subpath(folder if folder else keyword)
                if resolved:
                    return resolved
                if folder:
                    return os.path.join(self.USER_HOME, folder)
                return self.USER_HOME

        return None

    def _extract_folder_to_delete(self, message: str) -> Optional[str]:
        """Extract specific folder to delete."""
        msg = message.lower()

        # Pattern: "delete folder X" or "delete the folder X"
        match = re.search(r'\b(?:delete|elimina|rimuovi)\s+(?:the\s+)?(?:folder|cartella)\s+["\']?(\w+)["\']?', msg)
        if match:
            folder_name = match.group(1)
            # If the folder name matches the current context's basename, delete that folder
            if self._last_directory_context:
                base = os.path.basename(self._last_directory_context.get("path", "") or "")
                if base.lower() == folder_name.lower():
                    return self._last_directory_context["path"]
            # Check if it's a known folder
            context_resolved = self._resolve_context_subpath(folder_name)
            if context_resolved:
                return context_resolved
            if folder_name in self.FOLDER_MAP:
                return os.path.join(self.USER_HOME, self.FOLDER_MAP[folder_name])
            # Check conversation context for folder location
            target_folder = self._get_context_folder()
            if target_folder:
                return os.path.join(target_folder, folder_name.capitalize())

        # Pattern: "delete X folder"
        match = re.search(r'\b(?:delete|elimina|rimuovi)\s+(?:the\s+)?["\']?(\w+)["\']?\s+(?:folder|cartella)', msg)
        if match:
            folder_name = match.group(1)
            if self._last_directory_context:
                base = os.path.basename(self._last_directory_context.get("path", "") or "")
                if base.lower() == folder_name.lower():
                    return self._last_directory_context["path"]
            context_resolved = self._resolve_context_subpath(folder_name)
            if context_resolved:
                return context_resolved
            target_folder = self._get_context_folder()
            if target_folder:
                return os.path.join(target_folder, folder_name.capitalize())

        # Pattern: "delete the folder" with no name, use context
        if self._last_directory_context and re.search(r'\bdelete\s+(?:the\s+)?folder\b', msg):
            return self._last_directory_context["path"]

        return None

    def _get_context_folder(self) -> Optional[str]:
        """Get folder from recent conversation context."""
        if self._last_directory_context:
            return self._last_directory_context.get("path")

        # Look at recent messages for folder context
        for msg in reversed(self.conversation[-5:]):
            content = msg.get("content", "").lower()
            for keyword, folder in self.FOLDER_MAP.items():
                if keyword in content and folder:
                    return os.path.join(self.USER_HOME, folder)
        return f"{self.USER_HOME}/Desktop"  # Default

    def _extract_path(self, message: str) -> Optional[str]:
        """Extract file path from message."""
        # Absolute path
        match = re.search(r'["\']?(/[^\s"\']+\.[a-zA-Z0-9]+)["\']?', message)
        if match:
            return match.group(1)

        # Home path
        match = re.search(r'["\']?(~/[^\s"\']+)["\']?', message)
        if match:
            return os.path.expanduser(match.group(1))

        return None

    def _message_has_explicit_path(self, message: str) -> bool:
        """Check if a message contains an explicit absolute or home path."""
        return bool(re.search(r'["\']?(/[^\s"\']+)|["\']?(~/[^\s"\']+)', message))

    def _resolve_folder_alias(self, token: str) -> Optional[str]:
        """Resolve a folder alias like 'Docs' or 'Downloads' to an absolute path."""
        key = token.strip().strip("/").lower()
        if key in self.FOLDER_MAP:
            folder = self.FOLDER_MAP[key]
            return os.path.join(self.USER_HOME, folder) if folder else self.USER_HOME
        return None

    def _extract_destination_from_message(
        self,
        message: str,
        base_dir: str,
        source_name: str | None = None,
    ) -> Optional[str]:
        """Extract a destination path from a move/rename utterance."""
        dest_match = re.search(
            r'\b(?:to|into|in|as)\s+(?:just\s+|solo\s+)?["\']?([^\s"\']+)["\']?',
            message,
            re.IGNORECASE,
        )
        if not dest_match:
            return None

        dest_token = dest_match.group(1).strip()

        if os.path.isabs(dest_token) or dest_token.startswith("~"):
            return os.path.expanduser(dest_token)

        alias_path = self._resolve_folder_alias(dest_token)
        if alias_path:
            return os.path.join(alias_path, source_name) if source_name else alias_path

        msg_lower = message.lower()
        is_rename = "rename" in msg_lower or "rinomina" in msg_lower

        if "." in os.path.basename(dest_token):
            return os.path.join(base_dir, dest_token)

        if is_rename and source_name and "." in source_name:
            ext = os.path.splitext(source_name)[1]
            return os.path.join(base_dir, f"{dest_token}{ext}")

        resolved_subpath = self._resolve_context_subpath(dest_token)
        if resolved_subpath:
            return os.path.join(resolved_subpath, source_name) if source_name else resolved_subpath

        return os.path.join(base_dir, dest_token, source_name) if source_name else os.path.join(base_dir, dest_token)

    def _extract_filename(self, message: str) -> Optional[str]:
        """Extract filename from message."""
        patterns = [
            r'(?:called|named|chiamat[ao])\s+["\']?([a-zA-Z0-9_\-\.]+\.[a-zA-Z0-9]+)["\']?',
            r'file\s+["\']?([a-zA-Z0-9_\-\.]+\.[a-zA-Z0-9]+)["\']?',
            r'["\']([a-zA-Z0-9_\-\.]+\.[a-zA-Z0-9]+)["\']',
            r'\b([a-zA-Z0-9_\-\.]+\.[a-zA-Z0-9]+)\b',
        ]
        for p in patterns:
            match = re.search(p, message, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _extract_filename_from_context(self, message: str) -> Optional[str]:
        """Extract filename and join with current directory context if available."""
        name = self._extract_filename(message)
        if not name:
            # Try simpler pattern without extension mentioned explicitly
            simple = re.search(r'\bfile\s+(?:called|named)?\s*["\']?([\w\.-]+)["\']?', message, re.IGNORECASE)
            if simple:
                name = simple.group(1)
        if name and self._last_directory_context and self._last_directory_context.get("path"):
            return os.path.join(self._last_directory_context["path"], name)
        return name

    def _extract_foldername(self, message: str) -> Optional[str]:
        """Extract folder name from message."""
        patterns = [
            r'(?:folder|cartella|directory)\s+(?:called|named|chiamat[ao])?\s*["\']?([a-zA-Z0-9_\-]+)["\']?',
        ]
        for p in patterns:
            match = re.search(p, message, re.IGNORECASE)
            if match:
                name = match.group(1)
                # Filter out keywords
                if name.lower() not in ('named', 'called', 'new', 'nuovo', 'in', 'on', 'the'):
                    return name
        return None

    def _extract_content(self, message: str) -> str:
        """Extract file content from message."""
        patterns = [
            r'(?:content|contenuto|with|con)\s*[:\s]+["\'](.+?)["\']',
            r'(?:content|contenuto)\s+(.+?)$',
        ]
        for p in patterns:
            match = re.search(p, message, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    # === Response Cleaning ===

    def _clean_response(self, response: str) -> str:
        """Remove any tool artifacts from response."""
        cleaned = response

        # Remove tool JSON patterns
        patterns = [
            r'`+tool\{.*?\}`+',
            r'```tool.*?```',
            r'```json.*?```',
            r'\{["\']?tool["\']?\s*:.*?\}',
            r'\[Tool Result\]',
            r'\[TOOL RESULT\]',
            r'\[TOOL ERROR\]',
            r'Tool executed successfully\.?\s*Result:?\s*',
            r'Directory:\s*/[^\n]+\nTotal items:\s*\d+\s*',
        ]

        for p in patterns:
            cleaned = re.sub(p, '', cleaned, flags=re.DOTALL | re.IGNORECASE)

        # Clean whitespace
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

    def _clean_chunk(self, chunk: str) -> str:
        """Clean streaming chunk - filter tool syntax."""
        # Simple filter for obvious tool patterns
        if '```tool' in chunk or '"tool":' in chunk:
            return ""
        return chunk

    # === Model Management ===

    async def _ensure_model_ready(self, model_id: str):
        """Start model if not running."""
        if self.process_manager.is_running(model_id):
            return

        model = self.registry.get(model_id)
        if not model or not model.is_downloaded or not model.local_path:
            raise RuntimeError(f"Model {model_id} not available")

        logger.info(f"Starting model {model_id}...")
        await self.process_manager.start(
            model_id=model_id,
            model_path=Path(model.local_path),
            n_ctx=model.context_length,
        )

    # === Public Methods ===

    def get_last_routing(self) -> Optional[RoutingDecision]:
        return self._last_routing

    def get_last_tool_result(self) -> Optional[dict]:
        return self._last_tool_result

    def get_available_tools(self) -> list[dict]:
        if not self.tool_executor:
            return []
        return [
            {
                "id": t.name,
                "name": t.name,
                "description": t.description,
                "icon": self._tool_icon(t.category.value),
                "enabled": t.enabled and self.tools_enabled,
            }
            for t in self.tool_executor.registry.list_all()
        ]

    def set_tool_enabled(self, tool_id: str, enabled: bool) -> bool:
        """Enable or disable a tool by ID."""
        if not self.tool_executor:
            return False
        return self.tool_executor.registry.set_enabled(tool_id, enabled)

    def clear_conversation(self):
        self.conversation = []
        self._pending_action = None
        self._last_directory_context = None
        self._context.clear()

    def get_context(self) -> ConversationContext:
        """Get the conversation context for external access."""
        return self._context

    async def shutdown(self):
        logger.info("Shutting down Leonard...")
        await self.process_manager.stop_all()
        if self._memory_manager:
            await self._memory_manager.shutdown()
        self._initialized = False
        logger.info("Leonard shut down")

    def is_initialized(self) -> bool:
        return self._initialized

    def get_running_models(self) -> list[str]:
        return self.process_manager.list_running()

    def get_model_status(self, model_id: str) -> Optional[dict]:
        return self.process_manager.get_status(model_id)
