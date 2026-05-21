"""Pydantic schemas for sentinel alerts and policies."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from common.schemas.enums import InterventionAction, SentinelType, Severity


class SentinelAlertCreate(BaseModel):
    event_id: UUID | None = None
    tenant_id: str
    agent_id: str
    sentinel_type: SentinelType
    severity: Severity
    message: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class SentinelAlertResponse(BaseModel):
    id: UUID
    event_id: UUID | None
    tenant_id: str
    agent_id: str
    sentinel_type: SentinelType
    severity: Severity
    message: str
    details: dict[str, Any]
    action_taken: InterventionAction | None
    is_resolved: bool
    resolved_at: datetime | None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ResolveAlertRequest(BaseModel):
    action: InterventionAction


class AlertListResponse(BaseModel):
    alerts: list[SentinelAlertResponse]
    total: int


class PolicyCreate(BaseModel):
    tenant_id: str
    name: str = Field(min_length=1)
    description: str = ""
    sentinel_type: SentinelType
    severity: Severity
    action: InterventionAction
    config: dict[str, Any] = Field(default_factory=dict)


class PolicyResponse(BaseModel):
    id: UUID
    tenant_id: str
    name: str
    description: str
    sentinel_type: SentinelType
    severity: Severity
    action: InterventionAction
    is_active: bool
    config: dict[str, Any]
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class PolicyListResponse(BaseModel):
    policies: list[PolicyResponse]
    total: int
