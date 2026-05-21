"""SQLAlchemy model for tenant webhook endpoint registrations."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from common.models.base import Base, TimestampMixin


class WebhookEndpoint(Base, TimestampMixin):
    __tablename__ = "webhook_endpoints"

    id: Mapped[UUID] = mapped_column(sa.UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(sa.String(255), index=True)
    url: Mapped[str] = mapped_column(sa.String(2048))
    secret: Mapped[str] = mapped_column(sa.String(255))
    event_types: Mapped[list[str]] = mapped_column(sa.JSON)
    description: Mapped[str] = mapped_column(sa.Text)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    failure_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    last_delivered_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    def __init__(self, **kw: Any) -> None:
        kw.setdefault("is_active", True)
        kw.setdefault("event_types", ["*"])
        kw.setdefault("description", "")
        kw.setdefault("failure_count", 0)
        super().__init__(**kw)
