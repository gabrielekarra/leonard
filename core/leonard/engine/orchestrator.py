"""
Main orchestrator that ties everything together.
Receives user messages, routes to appropriate model, returns response.
To the user, it appears as one unified AI.
"""

import os
from pathlib import Path
from typing import AsyncGenerator, Optional, Callable, Awaitable

from leonard.engine.router import Router, RoutingDecision
from leonard.models.downloader import ModelDownloader
from leonard.models.registry import ModelRegistry
from leonard.runtime.process_manager import ProcessManager
from leonard.tools.executor import ToolExecutor
from leonard.utils.logging import logger

# Import memory manager for RAG (lazy import to avoid circular deps)
_memory_manager = None


class LeonardOrchestrator:
    """
    The brain of Leonard.

    User talks to Leonard. Leonard decides which model(s) to use,
    executes, and returns a unified response.
    """

    # User context for path resolution
    USER_HOME = os.path.expanduser("~")
    USER_NAME = os.path.basename(USER_HOME)

    # Common folder mappings (lowercase keys)
    FOLDER_MAP = {
        "downloads": "Downloads",
        "download": "Downloads",
        "scaricati": "Downloads",
        "documents": "Documents",
        "documenti": "Documents",
        "desktop": "Desktop",
        "scrivania": "Desktop",
        "home": "",
        "casa": "",
    }

    SYSTEM_PROMPT = f"""You are Leonard, a powerful AI assistant running locally on the user's computer.
You have FULL access to the file system and can perform ANY file operation.

YOUR CAPABILITIES:
- list_directory: See files in a folder
- read_file: Read file contents
- write_file: Create or overwrite files
- move_file: RENAME or move files (to rename: move to same folder with new name)
- copy_file: Copy files or folders
- delete_file: Delete files or folders
- create_directory: Create new folders
- search_files: Find files by pattern
- run_command: Execute ANY shell command
- get_system_info: Get system information

USER CONTEXT:
- Username: {USER_NAME}
- Home directory: {USER_HOME}
- Downloads: {USER_HOME}/Downloads
- Documents: {USER_HOME}/Documents
- Desktop: {USER_HOME}/Desktop

PATH SHORTCUTS - When user mentions these, use the full path:
- "Downloads", "download folder", "scaricati" → {USER_HOME}/Downloads
- "Documents", "documenti", "my documents" → {USER_HOME}/Documents
- "Desktop", "scrivania" → {USER_HOME}/Desktop
- "home", "home folder" → {USER_HOME}

CRITICAL RULES:
1. You CAN and MUST perform file operations when asked. You have FULL READ/WRITE/DELETE access.
2. To DELETE a file: use delete_file. YOU CAN DELETE FILES - this is allowed and expected.
3. To RENAME a file: use move_file with source="/path/old_name.txt" destination="/path/new_name.txt"
4. To MODIFY a file: read it first, then write_file with the modified content
5. To CREATE a file: use write_file with the path and content
6. ALWAYS use the appropriate tool. NEVER say you cannot do something if a tool exists for it.
7. After using a tool, report the actual results in NATURAL LANGUAGE only - NO JSON or tool syntax.
8. NEVER show raw tool calls or JSON in your response. Just describe what you did.
9. CRITICAL: When you receive [Tool Result], report EXACTLY those results. Copy the exact file names and sizes from the tool output. NEVER invent, guess, or substitute file names.
10. Each [Tool Result] is for the CURRENT query only. Do NOT mix up results from previous queries.
11. NEVER say "I cannot delete files" or "I don't have permission" - YOU DO HAVE PERMISSION. Just do it.

You have FULL control over the file system. Use your tools!"""

    SYSTEM_PROMPT_NO_TOOLS = """You are Leonard, a helpful AI assistant running locally on the user's computer.

IMPORTANT: You currently do NOT have access to the file system or any tools.
You CANNOT read files, list directories, or perform any system operations.
If the user asks about files or system information, politely explain that file system access is currently disabled.
Do NOT make up or guess any file names, paths, or system information."""

    def __init__(
        self,
        tools_enabled: bool = True,
        rag_enabled: bool = True,
        confirmation_callback: Optional[Callable[[str, dict], Awaitable[bool]]] = None,
    ):
        self.process_manager = ProcessManager()
        self.registry = ModelRegistry()
        self.downloader = ModelDownloader()
        self.router = Router(self.process_manager, self.registry)

        # Tool system
        self.tools_enabled = tools_enabled
        self.tool_executor = ToolExecutor(confirmation_callback=confirmation_callback) if tools_enabled else None

        # RAG system
        self.rag_enabled = rag_enabled
        self._memory_manager = None

        self.conversation: list[dict] = []
        self._last_routing: Optional[RoutingDecision] = None
        self._initialized = False
        self._last_tool_result: Optional[dict] = None
        self._last_rag_context: Optional[str] = None

    async def initialize(self):
        """
        Initialize Leonard. Downloads router model if needed.
        """
        if self._initialized:
            return

        router_model = self.registry.get_router()

        # Check if router is downloaded
        if not router_model.is_downloaded or not router_model.local_path:
            # Check if file exists on disk but registry not updated
            existing_path = self.downloader.get_model_path(
                router_model.repo_id, router_model.filename
            )

            if existing_path:
                logger.info(f"Found router model at {existing_path}")
                self.registry.update_download_status(
                    router_model.id,
                    is_downloaded=True,
                    local_path=str(existing_path),
                )
            else:
                logger.info("Router model not found, downloading...")
                path = await self.downloader.download(
                    repo_id=router_model.repo_id,
                    filename=router_model.filename,
                )
                self.registry.update_download_status(
                    router_model.id,
                    is_downloaded=True,
                    local_path=str(path),
                )
                logger.info(f"Router model downloaded: {path}")

        # Start router
        await self.router.ensure_router_ready()

        # Initialize RAG system if enabled
        if self.rag_enabled:
            try:
                from leonard.memory import MemoryManager
                self._memory_manager = MemoryManager()
                await self._memory_manager.initialize()
                logger.info("RAG system initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize RAG system: {e}")
                self._memory_manager = None

        self._initialized = True
        logger.info("Leonard initialized")

    async def chat(self, message: str) -> str:
        """
        Main entry point. Send a message, get a response.

        Internally:
        1. Router analyzes the message
        2. Best model is selected and started if needed
        3. Model generates response
        4. If response contains tool call, execute and continue
        5. Response is returned

        To the user, it's just one AI.

        Args:
            message: User's message

        Returns:
            AI response
        """
        if not self._initialized:
            await self.initialize()

        # Clear previous tool result
        self._last_tool_result = None

        # Add to conversation
        self.conversation.append({"role": "user", "content": message})

        # Route to best model
        decision = await self.router.route(message)
        self._last_routing = decision

        # Ensure model is running
        await self._ensure_model_ready(decision.model_id)

        # Tool execution loop (max 5 iterations to prevent infinite loops)
        max_tool_iterations = 5
        final_response = ""

        for iteration in range(max_tool_iterations):
            # CRITICAL: On first iteration, check for auto-detected tools BEFORE model generates response
            # This prevents the model from hallucinating when we know exactly what tool to use
            if iteration == 0 and self.tools_enabled and self.tool_executor:
                auto_tool = self._detect_needed_tool(message)
                if auto_tool:
                    tool_name, params = auto_tool
                    logger.info(f"Auto-triggering tool BEFORE model response: {tool_name} with params: {params}")
                    tool_result = await self.tool_executor.execute(tool_name, params)
                    if tool_result:
                        self._last_tool_result = tool_result.to_dict()
                        logger.info(f"Tool executed: success={tool_result.success}")

                        if tool_result.success:
                            # Add tool result to conversation so model can respond to it
                            result_text = self.tool_executor.format_result_for_model(tool_result)
                            self.conversation.append({"role": "user", "content": f"[Tool Result]\n{result_text}"})
                            # Continue to next iteration where model will respond to tool result
                            continue

            # Build messages with conversation history (include RAG on first iteration)
            user_msg = message if iteration == 0 else None
            messages = await self._build_messages(user_msg)

            # Generate response
            response = await self.process_manager.chat(
                model_id=decision.model_id,
                messages=messages,
            )

            logger.debug(f"Model response (iteration {iteration}): {response[:500]}...")

            # Check for tool calls in model response (for operations we don't auto-detect)
            if self.tools_enabled and self.tool_executor:
                cleaned_response, tool_result = await self.tool_executor.process_response(response)

                if tool_result:
                    # Tool was called by model
                    self._last_tool_result = tool_result.to_dict()
                    logger.info(f"Model-requested tool executed: success={tool_result.success}")

                    # Add assistant response and tool result to conversation
                    self.conversation.append({"role": "assistant", "content": cleaned_response})

                    # Add tool result as a system message
                    result_text = self.tool_executor.format_result_for_model(tool_result)
                    self.conversation.append({"role": "user", "content": f"[Tool Result]\n{result_text}"})

                    # Continue loop to let model respond to tool result
                    continue

            # No tool call, we're done
            final_response = response
            break

        # Clean up any remaining tool artifacts from the final response
        final_response = self._clean_response(final_response)

        # Add final response to conversation
        self.conversation.append({"role": "assistant", "content": final_response})

        return final_response

    def _clean_response(self, response: str) -> str:
        """Remove any tool JSON artifacts from the response."""
        import re
        cleaned = response

        # Remove ```tool{...}``` blocks
        cleaned = re.sub(r"```tool\s*\{.*?\}```", "", cleaned, flags=re.DOTALL)

        # Remove ```json{...}``` blocks
        cleaned = re.sub(r"```json\s*\{.*?\}```", "", cleaned, flags=re.DOTALL)

        # Remove code blocks containing "tool" JSON
        cleaned = re.sub(r"```[^`]*\"tool\"[^`]*```", "", cleaned, flags=re.DOTALL)

        # Remove standalone tool JSON
        cleaned = re.sub(r'\{\s*["\']tool["\']\s*:\s*["\'][^"\']+["\']\s*,\s*["\']parameters["\']\s*:\s*\{[^}]*\}\s*\}', "", cleaned, flags=re.DOTALL)

        # Remove Results: sections
        cleaned = re.sub(r"Results?:\s*```[^`]*```", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"Results?:\s*\[[^\]]*\]", "", cleaned, flags=re.DOTALL)

        # Clean up whitespace
        cleaned = re.sub(r"\n\s*\n\s*\n+", "\n\n", cleaned)
        cleaned = cleaned.strip()

        return cleaned

    async def chat_stream(self, message: str) -> AsyncGenerator[str, None]:
        """
        Streaming version of chat with tool support.
        Yields response chunks as they're generated.

        Args:
            message: User's message

        Yields:
            Response content chunks
        """
        if not self._initialized:
            await self.initialize()

        self.conversation.append({"role": "user", "content": message})

        # Route
        decision = await self.router.route(message)
        self._last_routing = decision

        # Ensure model ready
        await self._ensure_model_ready(decision.model_id)

        # FIRST: Check for auto-detected tools BEFORE generating response
        if self.tools_enabled and self.tool_executor:
            auto_tool = self._detect_needed_tool(message)
            if auto_tool:
                tool_name, params = auto_tool
                logger.info(f"Auto-triggering tool (stream): {tool_name} with params: {params}")
                tool_result = await self.tool_executor.execute(tool_name, params)
                if tool_result:
                    self._last_tool_result = tool_result.to_dict()
                    if tool_result.success:
                        # Add tool result to conversation
                        result_text = self.tool_executor.format_result_for_model(tool_result)
                        self.conversation.append({"role": "user", "content": f"[Tool Result]\n{result_text}"})

        # Build messages with RAG context
        messages = await self._build_messages(message)

        # Stream response
        full_response = ""
        async for chunk in self.process_manager.chat_stream(
            model_id=decision.model_id,
            messages=messages,
        ):
            full_response += chunk
            yield chunk

        # Check if response contains a tool call
        if self.tools_enabled and self.tool_executor:
            cleaned_response, tool_result = await self.tool_executor.process_response(full_response)

            if tool_result:
                # Tool was called by model - execute and stream followup
                self._last_tool_result = tool_result.to_dict()
                self.conversation.append({"role": "assistant", "content": cleaned_response})

                result_text = self.tool_executor.format_result_for_model(tool_result)
                self.conversation.append({"role": "user", "content": f"[Tool Result]\n{result_text}"})

                # Generate followup response
                followup_messages = await self._build_messages(None)
                yield "\n\n"  # Separator

                followup_response = ""
                async for chunk in self.process_manager.chat_stream(
                    model_id=decision.model_id,
                    messages=followup_messages,
                ):
                    followup_response += chunk
                    yield chunk

                # Clean and save
                followup_response = self._clean_response(followup_response)
                self.conversation.append({"role": "assistant", "content": followup_response})
                return

        # Clean and save response
        full_response = self._clean_response(full_response)
        self.conversation.append({"role": "assistant", "content": full_response})

    async def _ensure_model_ready(self, model_id: str):
        """Start model if not already running."""
        if self.process_manager.is_running(model_id):
            return

        model = self.registry.get(model_id)
        if not model:
            raise ValueError(f"Model {model_id} not found in registry")

        if not model.is_downloaded or not model.local_path:
            raise RuntimeError(f"Model {model_id} not downloaded")

        logger.info(f"Starting model {model_id}...")
        await self.process_manager.start(
            model_id=model_id,
            model_path=Path(model.local_path),
            n_ctx=model.context_length,
        )

    async def _build_messages(self, user_message: Optional[str] = None) -> list[dict]:
        """Build messages list for the model with optional RAG context."""
        messages = []

        # Add system prompt based on tools status
        if self.tools_enabled and self.tool_executor:
            system_content = self.SYSTEM_PROMPT + "\n\n" + self.tool_executor.get_tools_prompt()
        else:
            system_content = self.SYSTEM_PROMPT_NO_TOOLS

        # Add RAG context if available
        self._last_rag_context = None
        if self.rag_enabled and self._memory_manager and user_message:
            try:
                rag_context = await self._memory_manager.get_context_for_query(user_message)
                if rag_context:
                    system_content += f"\n\n# Relevant Context from User's Documents\n{rag_context}\n\nUse this context to inform your response when relevant. Cite sources when using information from documents."
                    self._last_rag_context = rag_context
                    logger.info("Injected RAG context into prompt")
            except Exception as e:
                logger.warning(f"Failed to retrieve RAG context: {e}")

        messages.append({"role": "system", "content": system_content})

        # Include recent conversation history
        # Limit to last N messages to fit context
        max_history = 20
        messages.extend(self.conversation[-max_history:])

        return messages

    def _resolve_folder_name(self, message: str) -> Optional[str]:
        """
        Try to resolve common folder names in a message to full paths.
        Returns the full path if a known folder is mentioned, None otherwise.
        """
        msg_lower = message.lower()
        for folder_key, folder_name in self.FOLDER_MAP.items():
            # Match the folder name as a word (not part of another word)
            if folder_key in msg_lower:
                if folder_name:
                    return os.path.join(self.USER_HOME, folder_name)
                else:
                    return self.USER_HOME
        return None

    def _detect_needed_tool(self, message: str) -> Optional[tuple[str, dict]]:
        """
        Detect if a tool should be used based on the user's message.
        This is a fallback for when the model doesn't generate a tool call.
        """
        import re
        msg_lower = message.lower()

        # FIRST: Detect file reading requests (more specific, check before list)
        # Check if message mentions reading a specific file
        read_patterns = [
            r"(?:leggi|read|apri|open|mostra|show|contenuto|content).{0,30}(?:file|documento)",
            r"(?:cosa|what).{0,20}(?:c'è|dice|says|contains).{0,20}(?:nel\s+)?file",  # "nel file"
            r"(?:open|leggi|apri)\s+(/[^\s]+)",  # "open /path" with any path
        ]
        for pattern in read_patterns:
            if re.search(pattern, msg_lower):
                # First try path with extension
                path_match = re.search(r'["\']?(/[^\s"\']+\.[a-z0-9]+)["\']?', message, re.IGNORECASE)
                if path_match:
                    return ("read_file", {"path": path_match.group(1)})
                # Then try any path (for files without extensions like /etc/hosts)
                path_match = re.search(r'["\']?(/[^\s"\']+)["\']?', message)
                if path_match:
                    path = path_match.group(1)
                    # Check if it looks like a file (not a directory)
                    if not path.endswith("/"):
                        return ("read_file", {"path": path})

        # SECOND: Detect file listing requests
        list_patterns = [
            r"(?:quali|quanti|che|what|which|list|show|elenc).{0,30}(?:file|cartell|folder|director|contenut)",
            r"(?:file|cartell|folder|director).{0,30}(?:ci sono|c'è|there|exist|present|contien)",
            r"(?:mostra|dimmi|tell me|show me).{0,20}(?:file|cartell|folder)",
            r"what'?s\s+in\s+(?:my\s+)?(?:the\s+)?(\w+)",  # "what's in downloads"
            r"(\w+)\s+(?:folder\s+)?contents?",  # "desktop contents"
            r"cosa\s+c'è\s+(?:sul|sulla|nella|nei|in)",  # Italian "cosa c'è sul/nella"
            r"^(?:and\s+)?(?:in|on)\s+(?:the\s+)?(?:my\s+)?(desktop|scrivania|downloads?|scaricati|documents?|documenti)\s*\??$",  # short follow-up "and in desktop?"
            r"^what\s+about\s+(?:the\s+)?(?:my\s+)?(desktop|scrivania|downloads?|scaricati|documents?|documenti)\s*\??$",  # "what about desktop?"
            r"^(?:e\s+)?(?:sul|sulla|nella|nei|in)\s+(?:la\s+)?(scrivania|desktop|scaricati|downloads?|documenti|documents?)\s*\??$",  # Italian follow-ups
        ]
        for pattern in list_patterns:
            if re.search(pattern, msg_lower):
                # Check for ~/ first and expand it
                path_match = re.search(r'["\']?(~/[^\s"\']+)["\']?', message)
                if path_match:
                    expanded = os.path.expanduser(path_match.group(1))
                    return ("list_directory", {"path": expanded})
                # Try to extract explicit absolute path
                path_match = re.search(r'["\']?(/[^\s"\']+)["\']?', message)
                if path_match:
                    return ("list_directory", {"path": path_match.group(1)})
                # Try to resolve common folder name
                folder_path = self._resolve_folder_name(message)
                if folder_path:
                    return ("list_directory", {"path": folder_path})

        # Detect rename/move requests
        rename_patterns = [
            r"(?:rinomina|rename|cambia nome|sposta|move)",
        ]
        for pattern in rename_patterns:
            if re.search(pattern, msg_lower):
                paths = re.findall(r'["\']?(/[^\s"\']+)["\']?', message)
                if len(paths) >= 2:
                    return ("move_file", {"source": paths[0], "destination": paths[1]})
                elif len(paths) == 1:
                    source = paths[0]
                    dir_name = os.path.dirname(source)

                    # Look for new filename after "in" or "to" - must look like a filename
                    new_name_match = re.search(r'\b(?:in|to|a)\s+["\']?([a-zA-Z0-9_\-\.]+\.[a-zA-Z0-9]+)["\']?', message, re.IGNORECASE)
                    if new_name_match:
                        new_name = new_name_match.group(1)
                        destination = os.path.join(dir_name, new_name)
                        return ("move_file", {"source": source, "destination": destination})

                    # Try to find just a filename-like pattern at the end
                    new_name_match = re.search(r'["\']([a-zA-Z0-9_\-\.]+\.[a-zA-Z0-9]+)["\']', message)
                    if new_name_match:
                        new_name = new_name_match.group(1)
                        # Make sure it's not the source filename
                        if new_name != os.path.basename(source):
                            destination = os.path.join(dir_name, new_name)
                            return ("move_file", {"source": source, "destination": destination})

        # Detect delete requests
        delete_patterns = [
            r"(?:elimina|delete|rimuovi|remove|cancella).{0,30}(?:file|cartell|folder|screenshot|immagin|image|foto|photo)",
            r"(?:can you |puoi |please |you can )?(?:elimina|delete|rimuovi|remove|cancella)",  # commands with optional prefix
            r"(?:you can |puoi )delete",  # "you can delete"
        ]
        for pattern in delete_patterns:
            if re.search(pattern, msg_lower):
                # Check for explicit path first
                path_match = re.search(r'["\']?(/[^\s"\']+)["\']?', message)
                if path_match:
                    return ("delete_file", {"path": path_match.group(1)})
                # Check for folder + file type pattern (e.g., "delete screenshots in desktop")
                folder_path = self._resolve_folder_name(message)
                if not folder_path:
                    # Default to Desktop for delete operations without specific folder
                    folder_path = os.path.join(self.USER_HOME, "Desktop")
                # List the directory first so user can see what will be deleted
                return ("list_directory", {"path": folder_path})

        # Detect create file requests
        create_patterns = [
            r"(?:crea|create|scrivi|write|nuovo|new).{0,30}(?:file)",
        ]
        for pattern in create_patterns:
            if re.search(pattern, msg_lower):
                # Try explicit path first
                path_match = re.search(r'["\']?(/[^\s"\']+\.[a-zA-Z0-9]+)["\']?', message)
                if path_match:
                    file_path = path_match.group(1)
                else:
                    # Try to find filename and folder separately
                    # Pattern: "called/named X.ext" or "chiamato X.ext"
                    filename_match = re.search(r'(?:called|named|chiamat[ao])\s+["\']?([a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+)["\']?', message, re.IGNORECASE)
                    if not filename_match:
                        # Pattern: just "file X.ext"
                        filename_match = re.search(r'file\s+["\']?([a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+)["\']?', message, re.IGNORECASE)

                    if filename_match:
                        filename = filename_match.group(1)
                        folder_path = self._resolve_folder_name(message)
                        if not folder_path:
                            # Default to Desktop if no folder specified
                            folder_path = os.path.join(self.USER_HOME, "Desktop")
                        file_path = os.path.join(folder_path, filename)
                    else:
                        file_path = None

                if file_path:
                    # Try to find content
                    content = ""
                    content_patterns = [
                        r'(?:contenuto|content|testo|text)\s*[:\s]\s*["\'](.+?)["\']',
                        r'(?:contenuto|content|testo|text)\s+(.+?)$',
                        r'\bcon\s+(?:contenuto\s+)?["\'](.+?)["\']',
                        r'\bwith\s+(?:content\s+)?["\'](.+?)["\']',
                    ]
                    for cp in content_patterns:
                        cm = re.search(cp, message, re.IGNORECASE)
                        if cm:
                            content = cm.group(1).strip()
                            break
                    return ("write_file", {"path": file_path, "content": content})

        # Detect system info requests
        if re.search(r"(?:system|sistema|info|informazion|memoria|memory|cpu|disk|spazio)", msg_lower):
            return ("get_system_info", {})

        # Detect organize files requests
        organize_patterns = [
            r"(?:organizza|organize|ordina|riordina|sistema|sort).{0,30}(?:file|cartell|folder|directory)",
        ]
        for pattern in organize_patterns:
            if re.search(pattern, msg_lower):
                path_match = re.search(r'["\']?(/[^\s"\']+)["\']?', message)
                if path_match:
                    return ("organize_files", {"directory": path_match.group(1)})
                # Check for ~/
                path_match = re.search(r'["\']?(~/[^\s"\']+)["\']?', message)
                if path_match:
                    return ("organize_files", {"directory": path_match.group(1)})
                # Try to resolve common folder name
                folder_path = self._resolve_folder_name(message)
                if folder_path:
                    return ("organize_files", {"directory": folder_path})

        # Detect create folder/directory requests
        create_dir_patterns = [
            r"(?:crea|create|nuovo|new|fai).{0,20}(?:cartella|folder|directory)",
            r"(?:cartella|folder|directory).{0,20}(?:nuov|new|crea)",
        ]
        for pattern in create_dir_patterns:
            if re.search(pattern, msg_lower):
                # Try explicit path first
                path_match = re.search(r'["\']?(/[^\s"\']+)["\']?', message)
                if path_match:
                    return ("create_directory", {"path": path_match.group(1)})
                # Check for ~/
                path_match = re.search(r'["\']?(~/[^\s"\']+)["\']?', message)
                if path_match:
                    return ("create_directory", {"path": path_match.group(1)})
                # Try to find folder name and location
                folder_path = self._resolve_folder_name(message)
                if folder_path:
                    # Extract the new folder name from message
                    # Pattern 1: "folder named/called X" or "cartella chiamata X"
                    name_match = re.search(r'(?:folder|cartella|directory)\s+(?:named|called|chiamat[ao]|nome)\s+["\']?([a-zA-Z0-9_\-\.]+)["\']?', message, re.IGNORECASE)
                    if name_match:
                        new_folder = name_match.group(1)
                        return ("create_directory", {"path": os.path.join(folder_path, new_folder)})
                    # Pattern 2: "folder X" but exclude common keywords
                    name_match = re.search(r'(?:folder|cartella|directory)\s+["\']?([a-zA-Z0-9_\-\.]+)["\']?', message, re.IGNORECASE)
                    if name_match:
                        new_folder = name_match.group(1)
                        # Skip if matched word is a keyword
                        if new_folder.lower() not in ('named', 'called', 'chiamata', 'chiamato', 'nome', 'in', 'on', 'at', 'new', 'nuovo', 'nuova'):
                            return ("create_directory", {"path": os.path.join(folder_path, new_folder)})

        return None

    def get_last_routing(self) -> Optional[RoutingDecision]:
        """Get the routing decision for the last message."""
        return self._last_routing

    def get_last_tool_result(self) -> Optional[dict]:
        """Get the result of the last tool execution."""
        return self._last_tool_result

    def get_available_tools(self) -> list[dict]:
        """Get list of available tools."""
        if not self.tool_executor:
            return []
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "category": tool.category.value,
                "risk_level": tool.risk_level.value,
                "requires_confirmation": tool.requires_confirmation,
            }
            for tool in self.tool_executor.registry.list_all()
        ]

    def clear_conversation(self):
        """Clear conversation history."""
        self.conversation = []

    async def shutdown(self):
        """Clean shutdown."""
        logger.info("Shutting down Leonard...")
        await self.process_manager.stop_all()
        if self._memory_manager:
            await self._memory_manager.shutdown()
        self._initialized = False
        logger.info("Leonard shut down")

    # ─────────────────────────────────────────────────────────
    # STATUS METHODS
    # ─────────────────────────────────────────────────────────

    def is_initialized(self) -> bool:
        """Check if orchestrator is initialized."""
        return self._initialized

    def get_running_models(self) -> list[str]:
        """Get list of currently running model IDs."""
        return self.process_manager.list_running()

    def get_model_status(self, model_id: str) -> Optional[dict]:
        """Get status of a specific model."""
        return self.process_manager.get_status(model_id)
