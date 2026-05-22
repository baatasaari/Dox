"""Schemas for the Agent Registry module."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AgentProfileCreate(BaseModel):
    tenant_id: str
    agent_id: str
    name: str
    description: str | None = None
    version: str = "1.0"
    capabilities: list[str] = Field(default_factory=list)
    tags: dict[str, str] = Field(default_factory=dict)


class AgentProfileUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    version: str | None = None
    capabilities: list[str] | None = None
    tags: dict[str, str] | None = None
    is_active: bool | None = None


class AgentProfileResponse(BaseModel):
    id: UUID
    tenant_id: str
    agent_id: str
    name: str
    description: str | None
    version: str
    capabilities: list[str]
    tags: dict[str, str]
    is_active: bool
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentProfileListResponse(BaseModel):
    agents: list[AgentProfileResponse]
    total: int


class HeartbeatResponse(BaseModel):
    agent_id: str
    last_seen_at: datetime
