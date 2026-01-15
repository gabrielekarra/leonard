"""Tools and Skills API routes."""

from fastapi import APIRouter, HTTPException

from leonard.api.schemas import Skill, SuccessResponse, Tool, ToolUpdateRequest
from leonard.utils.logging import logger

router = APIRouter(tags=["tools"])

# Mock data for MVP
MOCK_TOOLS: dict[str, dict] = {
    "filesystem": {
        "id": "filesystem",
        "name": "Filesystem",
        "description": "Read and write local files",
        "icon": "folder",
        "enabled": True,
    },
    "terminal": {
        "id": "terminal",
        "name": "Terminal",
        "description": "Execute shell commands",
        "icon": "terminal",
        "enabled": False,
    },
    "browser": {
        "id": "browser",
        "name": "Web Browser",
        "description": "Search and browse the web",
        "icon": "globe",
        "enabled": False,
    },
}

MOCK_SKILLS: dict[str, dict] = {
    "summarizer": {
        "id": "summarizer",
        "name": "Summarizer",
        "description": "Summarize documents and text",
        "active": True,
    },
    "translator": {
        "id": "translator",
        "name": "Translator",
        "description": "Translate between languages",
        "active": False,
    },
}


@router.get("/tools", response_model=list[Tool])
async def list_tools() -> list[Tool]:
    """List all available tools."""
    logger.info("Listing tools")
    return [Tool(**tool) for tool in MOCK_TOOLS.values()]


@router.put("/tools/{tool_id}", response_model=SuccessResponse)
async def update_tool(tool_id: str, request: ToolUpdateRequest) -> SuccessResponse:
    """Toggle a tool on/off."""
    if tool_id not in MOCK_TOOLS:
        raise HTTPException(status_code=404, detail="Tool not found")

    logger.info(f"Updating tool {tool_id}: enabled={request.enabled}")
    MOCK_TOOLS[tool_id]["enabled"] = request.enabled

    return SuccessResponse(
        success=True,
        message=f"Tool {tool_id} {'enabled' if request.enabled else 'disabled'}",
    )


@router.get("/skills", response_model=list[Skill])
async def list_skills() -> list[Skill]:
    """List all available skills."""
    logger.info("Listing skills")
    return [Skill(**skill) for skill in MOCK_SKILLS.values()]
