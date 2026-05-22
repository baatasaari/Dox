"""create agent_profiles table

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-22
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_profiles",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("capabilities", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("tags", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "agent_id", name="uq_agent_profiles_tenant_agent"),
    )
    op.create_index("ix_agent_profiles_tenant_id", "agent_profiles", ["tenant_id"])
    op.create_index("ix_agent_profiles_agent_id", "agent_profiles", ["agent_id"])


def downgrade() -> None:
    op.drop_table("agent_profiles")
