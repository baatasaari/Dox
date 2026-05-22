"""AgentProfile SQLAlchemy model."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from common.models.base import Base, TimestampMixin


class AgentProfile(Base, TimestampMixin):
    __tablename__ = "agent_profiles"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "agent_id", name="uq_agent_profiles_tenant_agent"),
    )

    id: Mapped[UUID] = mapped_column(sa.UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    version: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(
        sa.JSON, nullable=False, default=list
    )
    tags: Mapped[dict[str, str]] = mapped_column(sa.JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    def __init__(self, **kw: Any) -> None:
        kw["capabilities"] = list(kw.get("capabilities") or [])
        kw["tags"] = dict(kw.get("tags") or {})
        kw.setdefault("is_active", True)
        super().__init__(**kw)
