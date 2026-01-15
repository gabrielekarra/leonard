"""
Shell command tools for Leonard.
"""

import asyncio
import subprocess
from typing import Optional

from leonard.tools.base import (
    Tool,
    ToolCategory,
    ToolParameter,
    ToolResult,
    RiskLevel,
)
from leonard.utils.logging import logger


class RunCommandTool(Tool):
    """Execute a shell command."""

    # Commands that are always blocked
    BLOCKED_COMMANDS = [
        "rm -rf /",
        "rm -rf ~",
        "rm -rf /*",
        "sudo rm",
        "mkfs",
        "dd if=",
        ":(){:|:&};:",  # Fork bomb
        "chmod -R 777 /",
        "chown -R",
        "> /dev/sda",
        "mv ~ /dev/null",
    ]

    # Commands that require confirmation
    DANGEROUS_PATTERNS = [
        "sudo",
        "rm -rf",
        "rm -r",
        "chmod",
        "chown",
        "kill",
        "pkill",
        "killall",
        "shutdown",
        "reboot",
        "systemctl",
        "launchctl",
    ]

    def __init__(self):
        super().__init__(
            name="run_command",
            description="Execute a shell command and return the output. Use for system tasks like running scripts, checking system info, etc.",
            category=ToolCategory.SHELL,
            risk_level=RiskLevel.HIGH,
            requires_confirmation=True,
            parameters=[
                ToolParameter(
                    name="command",
                    type="string",
                    description="The shell command to execute",
                    required=True,
                ),
                ToolParameter(
                    name="working_directory",
                    type="string",
                    description="Working directory for the command (default: current directory)",
                    required=False,
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="Timeout in seconds (default: 30)",
                    required=False,
                    default=30,
                ),
            ],
        )

    def _is_blocked(self, command: str) -> Optional[str]:
        """Check if command is blocked. Returns reason if blocked."""
        command_lower = command.lower().strip()

        for blocked in self.BLOCKED_COMMANDS:
            if blocked in command_lower:
                return f"Command contains blocked pattern: {blocked}"

        return None

    def _is_dangerous(self, command: str) -> bool:
        """Check if command requires extra confirmation."""
        command_lower = command.lower()
        return any(pattern in command_lower for pattern in self.DANGEROUS_PATTERNS)

    async def execute(
        self,
        command: str,
        working_directory: Optional[str] = None,
        timeout: int = 30,
    ) -> ToolResult:
        # Check if command is blocked
        blocked_reason = self._is_blocked(command)
        if blocked_reason:
            return ToolResult(
                success=False,
                output=None,
                error=f"Command blocked for safety: {blocked_reason}",
            )

        try:
            logger.info(f"Executing command: {command}")

            # Run command
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_directory,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Command timed out after {timeout} seconds",
                )

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # Truncate very long output
            max_output = 10000
            if len(stdout_str) > max_output:
                stdout_str = stdout_str[:max_output] + "\n... (output truncated)"
            if len(stderr_str) > max_output:
                stderr_str = stderr_str[:max_output] + "\n... (output truncated)"

            if process.returncode == 0:
                return ToolResult(
                    success=True,
                    output={
                        "stdout": stdout_str,
                        "stderr": stderr_str,
                        "exit_code": process.returncode,
                    },
                )
            else:
                return ToolResult(
                    success=False,
                    output={
                        "stdout": stdout_str,
                        "stderr": stderr_str,
                        "exit_code": process.returncode,
                    },
                    error=f"Command failed with exit code {process.returncode}",
                )

        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


class GetSystemInfoTool(Tool):
    """Get system information."""

    def __init__(self):
        super().__init__(
            name="get_system_info",
            description="Get information about the system (OS, memory, disk space, etc.)",
            category=ToolCategory.SYSTEM,
            risk_level=RiskLevel.LOW,
            parameters=[],
        )

    async def execute(self) -> ToolResult:
        import platform
        import os

        try:
            info = {
                "os": platform.system(),
                "os_version": platform.version(),
                "os_release": platform.release(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "python_version": platform.python_version(),
                "hostname": platform.node(),
                "user": os.getenv("USER", "unknown"),
                "home": str(os.path.expanduser("~")),
                "cwd": os.getcwd(),
            }

            # Get memory info (macOS)
            if platform.system() == "Darwin":
                try:
                    result = subprocess.run(
                        ["sysctl", "-n", "hw.memsize"],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        mem_bytes = int(result.stdout.strip())
                        info["total_memory_gb"] = round(mem_bytes / (1024**3), 1)
                except Exception:
                    pass

            return ToolResult(success=True, output=info)

        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


# Export all shell tools
SHELL_TOOLS = [
    RunCommandTool(),
    GetSystemInfoTool(),
]
