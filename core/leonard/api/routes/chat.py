"""Chat API routes."""

import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from leonard.api import orchestrator_store
from leonard.api.orchestrator_store import get_orchestrator
from leonard.utils.logging import logger

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """Chat message request."""

    message: str
    conversation_id: str | None = None
    stream: bool = False


class ChatResponse(BaseModel):
    """Chat message response."""

    id: str
    content: str
    role: str
    model_used: str | None = None
    model_name: str | None = None
    routing_reason: str | None = None
    tool_used: dict | None = None  # Info about tool execution if any


@router.post("", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """
    Send a message to Leonard.
    Leonard automatically routes to the best model.
    """
    logger.info(f"Received message: {request.message[:50]}...")

    try:
        orch = await get_orchestrator()

        if request.conversation_id:
            orch.set_conversation_id(request.conversation_id)

        if request.stream:
            return StreamingResponse(
                _stream_response(orch, request.message),
                media_type="text/event-stream",
            )

        response = await orch.chat(request.message)
        routing = orch.get_last_routing()
        tool_result = orch.get_last_tool_result()

        return ChatResponse(
            id=str(uuid.uuid4()),
            content=response,
            role="assistant",
            model_used=routing.model_id if routing else None,
            model_name=routing.model_name if routing else None,
            routing_reason=routing.reason if routing else None,
            tool_used=tool_result,
        )

    except Exception as e:
        import traceback
        error_detail = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Chat error: {error_detail}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_detail)


async def _stream_response(orch: LeonardOrchestrator, message: str):
    """Stream chat response as SSE."""
    async for chunk in orch.chat_stream(message):
        yield f"data: {chunk}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/clear")
async def clear_chat():
    """Clear conversation history."""
    orch = await get_orchestrator()
    orch.clear_conversation()
    return {"status": "ok"}


@router.get("/routing")
async def get_routing():
    """Get last routing decision (for debugging/transparency)."""
    orch = await get_orchestrator()
    routing = orch.get_last_routing()

    if routing:
        return {
            "model_id": routing.model_id,
            "model_name": routing.model_name,
            "capability": routing.capability.value,
            "reason": routing.reason,
            "confidence": routing.confidence,
        }
    return {"routing": None}


@router.get("/status")
async def get_status():
    """Get orchestrator status."""
    if orchestrator_store.orchestrator is None:
        return {
            "initialized": False,
            "running_models": [],
            "tools_enabled": False,
        }

    return {
        "initialized": orchestrator_store.orchestrator.is_initialized(),
        "running_models": orchestrator_store.orchestrator.get_running_models(),
        "tools_enabled": orchestrator_store.orchestrator.tools_enabled,
    }


@router.get("/tools")
async def get_tools():
    """Get available tools."""
    orch = await get_orchestrator()
    return {
        "tools": orch.get_available_tools(),
        "enabled": orch.tools_enabled,
    }


class ToolsToggleRequest(BaseModel):
    """Request to toggle tools."""
    enabled: bool


@router.post("/tools/toggle")
async def toggle_tools(request: ToolsToggleRequest):
    """Enable or disable tools."""
    orch = await get_orchestrator()
    orch.tools_enabled = request.enabled
    # Clear conversation to prevent model from hallucinating based on old tool results
    orch.clear_conversation()
    return {
        "enabled": orch.tools_enabled,
        "message": f"Tools {'enabled' if request.enabled else 'disabled'}",
    }
