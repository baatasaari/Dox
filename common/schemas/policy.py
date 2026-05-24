"""Pydantic schemas for policy evaluation."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from common.schemas.enums import InterventionAction, SentinelType, Severity


class PolicyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    severity: Severity | None = None
    action: InterventionAction | None = None
    is_active: bool | None = None
    config: dict[str, Any] | None = None


class PolicyEvaluateRequest(BaseModel):
    tenant_id: str
    sentinel_type: SentinelType
    severity: Severity


class MatchedPolicy(BaseModel):
    id: UUID
    name: str
    action: InterventionAction

    model_config = {"from_attributes": True}


class PolicyEvaluationResult(BaseModel):
    tenant_id: str
    sentinel_type: SentinelType
    severity: Severity
    matched_count: int
    matched_policies: list[MatchedPolicy]
    action: InterventionAction
    is_blocked: bool
