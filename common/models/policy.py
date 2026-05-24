"""Policy SQLAlchemy model."""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from common.models.base import Base, TimestampMixin


class Policy(Base, TimestampMixin):
    __tablename__ = "policies"

    id: Mapped[UUID] = mapped_column(
        sa.UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[str] = mapped_column(sa.String(255), index=True)
    name: Mapped[str] = mapped_column(sa.String(255))
    description: Mapped[str] = mapped_column(sa.Text, default="")
    sentinel_type: Mapped[str] = mapped_column(sa.String(50), index=True)
    severity: Mapped[str] = mapped_column(sa.String(50))
    action: Mapped[str] = mapped_column(sa.String(50))
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(sa.JSON, default=dict)

    def __init__(self, **kw: Any) -> None:
        kw.setdefault("is_active", True)
        kw.setdefault("description", "")
        kw.setdefault("config", {})
        super().__init__(**kw)
