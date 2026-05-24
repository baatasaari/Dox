"""User SQLAlchemy model."""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from common.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        sa.UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    email: Mapped[str] = mapped_column(sa.String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(sa.String(255))
    tenant_id: Mapped[str] = mapped_column(sa.String(255), index=True)
    role: Mapped[str] = mapped_column(sa.String(50))
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)

    def __init__(self, **kw: Any) -> None:
        kw.setdefault("is_active", True)
        super().__init__(**kw)
