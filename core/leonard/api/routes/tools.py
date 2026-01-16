"""Tools and Skills API routes."""

from fastapi import APIRouter, HTTPException

from leonard.api.orchestrator_store import get_orchestrator
from leonard.api.schemas import Skill, SuccessResponse, Tool, ToolUpdateRequest
from leonard.utils.logging import logger

router = APIRouter(tags=["tools"])

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
    orch = await get_orchestrator()
    tools = orch.get_available_tools()
    return [Tool(**tool) for tool in tools]


@router.put("/tools/{tool_id}", response_model=SuccessResponse)
async def update_tool(tool_id: str, request: ToolUpdateRequest) -> SuccessResponse:
    """Toggle a tool on/off."""
    orch = await get_orchestrator()
    logger.info(f"Updating tool {tool_id}: enabled={request.enabled}")
    updated = orch.set_tool_enabled(tool_id, request.enabled)
    if not updated:
        raise HTTPException(status_code=404, detail="Tool not found")

    return SuccessResponse(
        success=True,
        message=f"Tool {tool_id} {'enabled' if request.enabled else 'disabled'}",
    )


@router.get("/skills", response_model=list[Skill])
async def list_skills() -> list[Skill]:
    """List all available skills."""
    logger.info("Listing skills")
    return [Skill(**skill) for skill in MOCK_SKILLS.values()]
