"""Pydantic models for API request/response schemas."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str


class ChatRequest(BaseModel):
    """Chat message request."""

    message: str
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    """Chat message response."""

    id: str
    content: str
    role: str


class AIModel(BaseModel):
    """AI model information."""

    id: str
    name: str
    description: str
    size: str
    installed: bool


class Tool(BaseModel):
    """MCP tool information."""

    id: str
    name: str
    description: str
    icon: str
    enabled: bool


class Skill(BaseModel):
    """Skill information."""

    id: str
    name: str
    description: str
    active: bool


class SuccessResponse(BaseModel):
    """Generic success response."""

    success: bool
    message: str | None = None


class ToolUpdateRequest(BaseModel):
    """Tool update request."""

    enabled: bool
