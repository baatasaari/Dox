"""create agent_baselines table

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-21
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_baselines",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("lookback_hours", sa.Integer, nullable=False),
        sa.Column("event_counts", sa.JSON, nullable=False),
        sa.Column("total_events", sa.Integer, nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
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
    op.create_index("ix_agent_baselines_tenant_id", "agent_baselines", ["tenant_id"])
    op.create_index("ix_agent_baselines_agent_id", "agent_baselines", ["agent_id"])
    op.create_index(
        "ix_agent_baselines_tenant_agent",
        "agent_baselines",
        ["tenant_id", "agent_id"],
    )


def downgrade() -> None:
    op.drop_table("agent_baselines")
