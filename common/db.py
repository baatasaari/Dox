"""Async database engine and session dependency."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from common.config import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db() -> None:
    global _engine, _session_factory
    _engine = create_async_engine(
        settings.database.url,
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def close_db() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if _session_factory is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    async with _session_factory() as session:
        yield session
