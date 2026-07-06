"""Module F — Database resilience under extreme conditions.

What this proves
----------------
1. Pool exhaustion:
   A pool capped at 2 connections raises ``sqlalchemy.exc.TimeoutError`` when a
   third checkout is attempted, and it does so within the configured timeout window.

2. Session isolation (READ COMMITTED):
   An uncommitted write in Session A is invisible to Session B.
   After Session A commits, Session B's next query sees the row.
"""
from __future__ import annotations

import time
from uuid import uuid4

import pytest
import sqlalchemy.exc
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from common.models.agent import AgentProfile

TEST_DB_URL = "postgresql+asyncpg://dox:dox_dev@localhost:5432/dox_test"


def _uid() -> str:
    return uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Pool exhaustion
# ---------------------------------------------------------------------------


class TestConnectionPoolExhaustion:
    """Checking out beyond pool capacity raises within the configured timeout."""

    async def test_third_checkout_raises_timeout_error(
        self, apply_migrations: None
    ) -> None:
        engine = create_async_engine(
            TEST_DB_URL,
            pool_size=2,
            max_overflow=0,
            pool_timeout=0.1,
        )
        conn1 = await engine.connect()
        conn2 = await engine.connect()

        try:
            start = time.monotonic()
            with pytest.raises(sqlalchemy.exc.TimeoutError):
                await engine.connect()
            elapsed = time.monotonic() - start
            assert elapsed < 0.5, (
                f"Pool timeout should fire within ~0.1 s, took {elapsed:.3f}s"
            )
        finally:
            await conn1.close()
            await conn2.close()
            await engine.dispose()


# ---------------------------------------------------------------------------
# READ COMMITTED isolation
# ---------------------------------------------------------------------------


class TestReadCommittedIsolation:
    """Uncommitted rows are invisible to other sessions (PostgreSQL default isolation)."""

    async def test_uncommitted_write_invisible_until_commit(
        self, real_engine: AsyncEngine
    ) -> None:
        agent_id = f"isol-agent-{_uid()}"

        # Session A: open an explicit transaction, flush an INSERT, keep it open.
        async with AsyncSession(real_engine) as sess_a:
            async with sess_a.begin():
                sess_a.add(
                    AgentProfile(
                        tenant_id="isol-tenant",
                        agent_id=agent_id,
                        name="IsolTest",
                        version="1.0",
                    )
                )
                await sess_a.flush()  # SQL sent but NOT committed yet

                # Session B has its own connection — must NOT see A's row.
                async with AsyncSession(real_engine) as sess_b:
                    result = await sess_b.execute(
                        select(AgentProfile).where(
                            AgentProfile.agent_id == agent_id
                        )
                    )
                    assert result.scalars().all() == [], (
                        "READ COMMITTED isolation breached:"
                        " uncommitted row from Session A is visible to Session B"
                    )

        # `sess_a.begin()` context committed on successful exit.

        # Session B now sees A's committed row.
        async with AsyncSession(real_engine) as sess_b:
            result = await sess_b.execute(
                select(AgentProfile).where(AgentProfile.agent_id == agent_id)
            )
            rows = result.scalars().all()
            assert len(rows) == 1

        # Cleanup.
        async with AsyncSession(real_engine) as sess_cleanup:
            async with sess_cleanup.begin():
                await sess_cleanup.execute(
                    delete(AgentProfile).where(AgentProfile.agent_id == agent_id)
                )
