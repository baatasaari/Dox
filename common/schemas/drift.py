"""Pydantic schemas for drift detection and behavioral baselines."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BaselineCreate(BaseModel):
    tenant_id: str
    agent_id: str
    lookback_hours: int = Field(default=24, ge=1, le=720)


class BaselineResponse(BaseModel):
    id: UUID
    tenant_id: str
    agent_id: str
    lookback_hours: int
    event_counts: dict[str, int]
    total_events: int
    computed_at: datetime
    is_active: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class BaselineListResponse(BaseModel):
    baselines: list[BaselineResponse]
    total: int


class EventTypeDeviation(BaseModel):
    event_type: str
    baseline_freq: float
    recent_freq: float
    delta: float


class DriftScore(BaseModel):
    tenant_id: str
    agent_id: str
    score: float
    severity: str
    recent_event_count: int
    baseline_total_events: int
    deviations: list[EventTypeDeviation]


class AnalyzeRequest(BaseModel):
    tenant_id: str
    agent_id: str
    lookback_hours: int = Field(default=1, ge=1, le=168)


class DriftReportResponse(BaseModel):
    drift_score: DriftScore
    baseline_id: UUID | None
    alert_created: bool
