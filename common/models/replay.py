"""SQLAlchemy model for persisted session-replay records."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from common.models.base import Base, TimestampMixin


class SessionReplay(Base, TimestampMixin):
    """Persistent record of a session playback — metadata and accumulated state."""

    __tablename__ = "session_replays"

    id: Mapped[UUID] = mapped_column(
        sa.UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[str] = mapped_column(
        sa.String(255), nullable=False, index=True
    )
    # The original session whose events are being replayed.
    original_session_id: Mapped[str] = mapped_column(
        sa.String(255), nullable=False, index=True
    )
    agent_id: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(500), nullable=False)

    # Lifecycle: pending → running → paused | completed | failed
    status: Mapped[str] = mapped_column(
        sa.String(50), nullable=False, default="pending"
    )

    # Frame counts.
    total_events: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    current_position: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0
    )

    # 0.0 = manual step-through; positive float = realtime multiplier.
    speed_factor: Mapped[float] = mapped_column(
        sa.Float, nullable=False, default=0.0
    )

    # Timestamps copied from the original session's first / last events.
    original_started_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    original_ended_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    original_duration_seconds: Mapped[float | None] = mapped_column(
        sa.Float, nullable=True
    )

    # Ordered list of frame dicts:
    #   {"seq": int, "event_id": str, "event_type": str,
    #    "timestamp": iso, "elapsed_seconds": float}
    replay_log: Mapped[list[Any]] = mapped_column(
        sa.JSON, nullable=False, default=list
    )

    # Accumulated state snapshot at current_position (updated by step/run).
    context_window: Mapped[dict[str, Any]] = mapped_column(
        sa.JSON, nullable=False, default=dict
    )

    def __init__(self, **kw: Any) -> None:
        kw.setdefault("id", uuid4())
        kw.setdefault("status", "pending")
        kw.setdefault("total_events", 0)
        kw.setdefault("current_position", 0)
        kw.setdefault("speed_factor", 0.0)
        kw.setdefault("replay_log", [])
        kw.setdefault("context_window", {})
        super().__init__(**kw)
