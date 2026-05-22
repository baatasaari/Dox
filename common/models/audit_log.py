"""SQLAlchemy model for the governance audit trail — append-only action records."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from common.models.base import Base


class AuditEntry(Base):
    """Append-only record of every significant platform governance action."""

    __tablename__ = "audit_entries"

    id: Mapped[UUID] = mapped_column(sa.UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(sa.String(255), index=True, nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(sa.UUID(as_uuid=True), nullable=True)
    actor_email: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    action: Mapped[str] = mapped_column(sa.String(100), index=True, nullable=False)
    resource_type: Mapped[str] = mapped_column(sa.String(100), index=True, nullable=False)
    resource_id: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    summary: Mapped[str] = mapped_column(sa.Text, nullable=False)
    extra: Mapped[dict[str, Any]] = mapped_column(sa.JSON, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )

    def __init__(self, **kw: Any) -> None:
        kw.setdefault("id", uuid4())
        kw.setdefault("extra", {})
        kw.setdefault("actor_email", "system")
        super().__init__(**kw)
