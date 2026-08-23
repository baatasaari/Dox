"""Module B — Alembic migration chain integrity under real PostgreSQL.

What this proves
----------------
1. The revision graph has exactly one head (no divergent branches).
2. Every revision in the chain has a single parent — no merge commits.
3. All expected tables exist after ``alembic upgrade head``.
4. ``alembic_version`` records the correct head revision.
5. Re-running ``upgrade head`` when already at head is a safe no-op.
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command

_EXPECTED_REVISION_COUNT = 9
_EXPECTED_HEAD = "0009"

_EXPECTED_TABLES = {
    "events",
    "tenant_quotas",
    "agent_profiles",
    "audit_entries",
    "session_replays",
}


# ---------------------------------------------------------------------------
# Chain structure (pure Python — no DB needed)
# ---------------------------------------------------------------------------


class TestMigrationChain:
    """The Alembic revision graph is a simple linear chain with a single head."""

    def test_single_head(self) -> None:
        cfg = Config("alembic.ini")
        scripts = ScriptDirectory.from_config(cfg)
        heads = scripts.get_heads()
        assert len(heads) == 1, f"Expected 1 head, got {len(heads)}: {heads}"

    def test_chain_is_linear_no_branches(self) -> None:
        """Walk from head to base; each revision must have exactly one parent."""
        cfg = Config("alembic.ini")
        scripts = ScriptDirectory.from_config(cfg)
        (head,) = scripts.get_heads()

        current: str | None = head
        visited: list[str] = []
        while current is not None:
            rev = scripts.get_revision(current)
            visited.append(rev.revision)
            if rev.down_revision is None:
                break
            if isinstance(rev.down_revision, tuple):
                pytest.fail(
                    f"Revision {rev.revision} has multiple parents"
                    f" {rev.down_revision!r} — chain is not linear."
                )
            current = rev.down_revision

        assert len(visited) == _EXPECTED_REVISION_COUNT, (
            f"Expected {_EXPECTED_REVISION_COUNT} revisions, "
            f"found {len(visited)}: {visited}"
        )

    def test_upgrade_head_is_idempotent(self, apply_migrations: None) -> None:
        """Running upgrade head when already at head must succeed (no-op)."""
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")


# ---------------------------------------------------------------------------
# Table / schema existence (requires a live DB connection)
# ---------------------------------------------------------------------------


class TestTableExistenceAfterUpgrade:
    """After ``upgrade head`` every expected table is present in the public schema."""

    async def test_all_core_tables_exist(self, db_session: AsyncSession) -> None:
        result = await db_session.execute(
            sa.text(
                "SELECT table_name"
                " FROM information_schema.tables"
                " WHERE table_schema = 'public'"
            )
        )
        tables = {row[0] for row in result.fetchall()}
        missing = _EXPECTED_TABLES - tables
        assert not missing, f"Tables missing after upgrade head: {missing}"

    async def test_alembic_version_at_head(self, db_session: AsyncSession) -> None:
        result = await db_session.execute(
            sa.text("SELECT version_num FROM alembic_version")
        )
        version = result.scalar_one_or_none()
        assert version == _EXPECTED_HEAD, (
            f"Expected alembic version {_EXPECTED_HEAD!r}, got {version!r}"
        )
