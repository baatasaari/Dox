"""create audit_entries table

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-22
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_entries",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("actor_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_email", sa.String(255), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("extra", sa.JSON, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_entries_tenant_id", "audit_entries", ["tenant_id"])
    op.create_index("ix_audit_entries_action", "audit_entries", ["action"])
    op.create_index("ix_audit_entries_resource_type", "audit_entries", ["resource_type"])
    op.create_index(
        "ix_audit_entries_tenant_created",
        "audit_entries",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("audit_entries")
