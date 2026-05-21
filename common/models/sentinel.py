"""SentinelAlert SQLAlchemy model."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from common.models.base import Base, TimestampMixin


class SentinelAlert(Base, TimestampMixin):
    __tablename__ = "sentinel_alerts"

    id: Mapped[UUID] = mapped_column(
        sa.UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    event_id: Mapped[UUID | None] = mapped_column(
        sa.UUID(as_uuid=True), nullable=True, index=True
    )
    tenant_id: Mapped[str] = mapped_column(sa.String(255), index=True)
    agent_id: Mapped[str] = mapped_column(sa.String(255), index=True)
    sentinel_type: Mapped[str] = mapped_column(sa.String(50), index=True)
    severity: Mapped[str] = mapped_column(sa.String(50), index=True)
    message: Mapped[str] = mapped_column(sa.Text)
    details: Mapped[dict[str, Any]] = mapped_column(sa.JSON)
    action_taken: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    is_resolved: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    def __init__(self, **kw: Any) -> None:
        kw.setdefault("is_resolved", False)
        kw.setdefault("details", {})
        super().__init__(**kw)
