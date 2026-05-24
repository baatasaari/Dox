"""Tenant SQLAlchemy model."""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from common.models.base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(
        sa.UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    slug: Mapped[str] = mapped_column(sa.String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(sa.String(255))
    subscription_tier: Mapped[str] = mapped_column(
        sa.String(50), default="starter"
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)

    def __init__(self, **kw: Any) -> None:
        kw.setdefault("subscription_tier", "starter")
        kw.setdefault("is_active", True)
        super().__init__(**kw)
