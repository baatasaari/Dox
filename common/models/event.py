"""SQLAlchemy model for persisted CanonicalEvents."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from common.models.base import Base, TimestampMixin
from common.schemas.events import CanonicalEvent
from common.schemas.validators import compute_payload_hash


class EventRecord(Base, TimestampMixin):
    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(
        sa.UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    event_id: Mapped[UUID] = mapped_column(
        sa.UUID(as_uuid=True), unique=True, index=True
    )
    trace_id: Mapped[UUID] = mapped_column(sa.UUID(as_uuid=True), index=True)
    session_id: Mapped[str] = mapped_column(sa.String(255), index=True)
    tenant_id: Mapped[str] = mapped_column(sa.String(255), index=True)
    agent_id: Mapped[str] = mapped_column(sa.String(255), index=True)
    agent_version: Mapped[str] = mapped_column(sa.String(100))
    event_type: Mapped[str] = mapped_column(sa.String(100), index=True)
    environment: Mapped[str] = mapped_column(sa.String(50))
    timestamp: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), index=True)
    client_timestamp: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    schema_version: Mapped[str] = mapped_column(sa.String(20))
    payload: Mapped[dict[str, Any]] = mapped_column(sa.JSON)
    raw_event: Mapped[dict[str, Any]] = mapped_column(sa.JSON)
    payload_hash: Mapped[str | None] = mapped_column(sa.String(64))

    @classmethod
    def from_canonical(cls, event: CanonicalEvent) -> EventRecord:
        return cls(
            id=uuid4(),
            event_id=event.event_id,
            trace_id=event.trace_id,
            session_id=event.session_id,
            tenant_id=event.tenant_id,
            agent_id=event.agent_id,
            agent_version=event.agent_version,
            event_type=event.event_type,
            environment=event.environment,
            timestamp=event.timestamp,
            client_timestamp=event.client_timestamp,
            schema_version=event.schema_version,
            payload=event.payload,
            raw_event=event.model_dump(mode="json"),
            payload_hash=event.payload_hash or compute_payload_hash(event.payload),
        )
