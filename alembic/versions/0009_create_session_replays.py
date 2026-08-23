"""create session_replays table

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-23
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_replays",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("original_session_id", sa.String(255), nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column(
            "status", sa.String(50), nullable=False, server_default="pending"
        ),
        sa.Column("total_events", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "current_position", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "speed_factor", sa.Float, nullable=False, server_default="0.0"
        ),
        sa.Column(
            "original_started_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "original_ended_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("original_duration_seconds", sa.Float, nullable=True),
        # JSON columns: replay_log is list[frame], context_window is accumulated state
        sa.Column(
            "replay_log", sa.JSON, nullable=False, server_default="[]"
        ),
        sa.Column(
            "context_window", sa.JSON, nullable=False, server_default="{}"
        ),
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
    op.create_index(
        "ix_session_replays_tenant_id", "session_replays", ["tenant_id"]
    )
    op.create_index(
        "ix_session_replays_original_session_id",
        "session_replays",
        ["original_session_id"],
    )
    op.create_index(
        "ix_session_replays_status", "session_replays", ["status"]
    )
    op.create_index(
        "ix_session_replays_tenant_status",
        "session_replays",
        ["tenant_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("session_replays")
