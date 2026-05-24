"""Request and response schemas for the ingestion service."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from common.schemas.events import CanonicalEvent


class IngestResponse(BaseModel):
    event_id: UUID
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["accepted"] = "accepted"


class BatchIngestRequest(BaseModel):
    events: list[CanonicalEvent] = Field(min_length=1, max_length=100)


class BatchIngestResponse(BaseModel):
    accepted: int
    rejected: int = 0
    event_ids: list[UUID]
