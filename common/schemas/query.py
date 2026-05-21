"""Pydantic schemas for event query and audit endpoints."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from common.schemas.enums import Environment, EventType


class EventFilter(BaseModel):
    tenant_id: str
    agent_id: str | None = None
    event_type: EventType | None = None
    environment: Environment | None = None
    session_id: str | None = None
    from_ts: datetime | None = None
    to_ts: datetime | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class EventSummary(BaseModel):
    id: UUID
    event_id: UUID
    tenant_id: str
    agent_id: str
    event_type: str
    environment: str
    timestamp: datetime
    payload_hash: str | None
    session_id: str
    trace_id: UUID
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class PaginatedEventsResponse(BaseModel):
    events: list[EventSummary]
    total: int
    limit: int
    offset: int


class RecordIntegrityResponse(BaseModel):
    record_id: str
    event_id: str
    status: str
    stored_hash: str | None
    computed_hash: str


class IntegrityReportResponse(BaseModel):
    tenant_id: str
    total_checked: int
    passed: int
    failed: int
    is_clean: bool
    records: list[RecordIntegrityResponse]
