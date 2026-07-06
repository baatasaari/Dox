"""Module A — Real PostgreSQL test harness.

Every integration test that needs a real database depends on ``db_session``.
The design:

* ``apply_migrations``  — session-scoped, sync.  Runs ``alembic upgrade head``
  once for the whole test session; ``downgrade base`` on teardown (proves both
  directions of every migration).
* ``db_session``        — function-scoped, async.  One real connection per test;
  the outer transaction is *always* rolled back, so no data survives between
  tests.  Service-layer ``commit()`` calls create savepoints instead of real
  commits thanks to ``join_transaction_mode="create_savepoint"``.

Prerequisites
-------------
Docker Compose must be running (``make dev``).  The ``dox_test`` database is
created automatically on the first run.
"""
from __future__ import annotations

import asyncio
import os

# Override BEFORE any common.* import so pydantic-settings reads the right URL.
# The top-level tests/conftest.py uses setdefault (wrong credentials); we
# override unconditionally here.
os.environ["DOX_DATABASE__URL"] = "postgresql+asyncpg://dox:dox_dev@localhost:5432/dox_test"
os.environ.setdefault("DOX_SECRET_KEY", "integration-test-secret-key")

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from alembic.config import Config

TEST_DB_URL = "postgresql+asyncpg://dox:dox_dev@localhost:5432/dox_test"
# Connect to the system DB to issue CREATE DATABASE (must be outside a txn).
_POSTGRES_URL = "postgresql+asyncpg://dox:dox_dev@localhost:5432/postgres"


# ---------------------------------------------------------------------------
# Internal helpers (sync wrappers around async bootstrap operations)
# ---------------------------------------------------------------------------

async def _create_db_if_missing() -> None:
    """Create dox_test if it doesn't exist; idempotent."""
    engine = create_async_engine(_POSTGRES_URL, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        row = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'dox_test'")
        )
        if row.scalar_one_or_none() is None:
            await conn.execute(text("CREATE DATABASE dox_test"))
    await engine.dispose()


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def apply_migrations() -> None:  # type: ignore[return]
    """Apply all Alembic migrations once; downgrade on teardown.

    The downgrade pass verifies that every ``down_revision`` chain is sound —
    i.e., a production rollback won't fail halfway through.
    """
    asyncio.run(_create_db_if_missing())

    # alembic/env.py reads settings.database.url at runtime; that now resolves
    # to TEST_DB_URL because we overrode DOX_DATABASE__URL above.
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    yield
    command.downgrade(cfg, "base")


# ---------------------------------------------------------------------------
# Function-scoped fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session(apply_migrations: None) -> AsyncSession:  # type: ignore[return]
    """Yield a real AsyncSession bound to a transaction that is always rolled back.

    Service-layer calls to ``session.commit()`` create a SAVEPOINT and release
    it (a pseudo-commit visible within the test) instead of writing to the DB.
    The outer ``conn.rollback()`` undoes everything at the end of each test.
    """
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()
    await engine.dispose()
