"""create tenant_quotas table

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-21
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_quotas",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False, unique=True),
        sa.Column("subscription_tier", sa.String(50), nullable=False),
        sa.Column("daily_limit", sa.Integer, nullable=False),
        sa.Column("monthly_limit", sa.Integer, nullable=False),
        sa.Column("events_today", sa.Integer, nullable=False, server_default="0"),
        sa.Column("events_this_month", sa.Integer, nullable=False, server_default="0"),
        sa.Column("day_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("month_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_tenant_quotas_tenant_id", "tenant_quotas", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("tenant_quotas")
