"""SQLAlchemy model for agent behavioral baselines."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from common.models.base import Base, TimestampMixin


class AgentBaseline(Base, TimestampMixin):
    __tablename__ = "agent_baselines"

    id: Mapped[UUID] = mapped_column(sa.UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(sa.String(255), index=True)
    agent_id: Mapped[str] = mapped_column(sa.String(255), index=True)
    lookback_hours: Mapped[int] = mapped_column(sa.Integer)
    event_counts: Mapped[dict[str, Any]] = mapped_column(sa.JSON)
    total_events: Mapped[int] = mapped_column(sa.Integer)
    computed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)

    def __init__(self, **kw: Any) -> None:
        kw.setdefault("is_active", True)
        kw.setdefault("event_counts", {})
        super().__init__(**kw)
