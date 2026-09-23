"""Schemas for the what-if assistant chat endpoint."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.scenario import ScenarioResult


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = Field(None, max_length=64, description="Omit to start a new conversation")


class ChatResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    session_id: str
    reply_markdown: str
    scenario: ScenarioResult | None = None
    incidents: list[dict[str, Any]] = []
    villages: list[dict[str, Any]] = []
    alert_preview: str | None = None
    tools_used: list[str] = []
    model: str


class ChatHistoryItem(BaseModel):
    role: str
    text: str
