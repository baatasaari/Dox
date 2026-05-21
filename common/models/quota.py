"""SQLAlchemy model for per-tenant event quota tracking."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from common.models.base import Base, TimestampMixin


class TenantQuota(Base, TimestampMixin):
    __tablename__ = "tenant_quotas"

    id: Mapped[UUID] = mapped_column(sa.UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(sa.String(255), unique=True, index=True)
    subscription_tier: Mapped[str] = mapped_column(sa.String(50))
    daily_limit: Mapped[int] = mapped_column(sa.Integer)
    monthly_limit: Mapped[int] = mapped_column(sa.Integer)
    events_today: Mapped[int] = mapped_column(sa.Integer, default=0)
    events_this_month: Mapped[int] = mapped_column(sa.Integer, default=0)
    day_window_start: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    month_window_start: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))

    def __init__(self, **kw: Any) -> None:
        now = datetime.now(UTC)
        kw.setdefault("events_today", 0)
        kw.setdefault("events_this_month", 0)
        kw.setdefault("day_window_start", now)
        kw.setdefault("month_window_start", now)
        super().__init__(**kw)
