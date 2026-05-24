"""create sentinel_alerts and policies tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-21
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sentinel_alerts",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("sentinel_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(50), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("details", sa.JSON, nullable=False),
        sa.Column("action_taken", sa.String(50), nullable=True),
        sa.Column("is_resolved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_sentinel_alerts_event_id", "sentinel_alerts", ["event_id"])
    op.create_index("ix_sentinel_alerts_tenant_id", "sentinel_alerts", ["tenant_id"])
    op.create_index("ix_sentinel_alerts_agent_id", "sentinel_alerts", ["agent_id"])
    op.create_index(
        "ix_sentinel_alerts_sentinel_type", "sentinel_alerts", ["sentinel_type"]
    )
    op.create_index("ix_sentinel_alerts_severity", "sentinel_alerts", ["severity"])

    op.create_table(
        "policies",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("sentinel_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(50), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("config", sa.JSON, nullable=False),
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
    op.create_index("ix_policies_tenant_id", "policies", ["tenant_id"])
    op.create_index("ix_policies_sentinel_type", "policies", ["sentinel_type"])


def downgrade() -> None:
    op.drop_table("policies")
    op.drop_table("sentinel_alerts")
