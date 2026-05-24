"""Pydantic schemas for the governance audit trail."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AuditEntryCreate(BaseModel):
    tenant_id: str
    actor_id: UUID | None = None
    actor_email: str = "system"
    action: str = Field(min_length=1, max_length=100)
    resource_type: str = Field(min_length=1, max_length=100)
    resource_id: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1)
    extra: dict[str, Any] = Field(default_factory=dict)


class AuditEntryResponse(BaseModel):
    id: UUID
    tenant_id: str
    actor_id: UUID | None
    actor_email: str
    action: str
    resource_type: str
    resource_id: str
    summary: str
    extra: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditListResponse(BaseModel):
    entries: list[AuditEntryResponse]
    total: int
    limit: int
    offset: int
