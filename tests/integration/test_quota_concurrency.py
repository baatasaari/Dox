"""Module D — Quota enforcement under concurrent PostgreSQL writers.

What this proves
----------------
1. Lost-update prevention:
   Twenty concurrent ``check_and_increment`` calls — each in its own session —
   must all be counted.  Without ``SELECT FOR UPDATE``, concurrent readers would
   each see ``events_today=0``, all write ``1``, and only one increment would
   survive.  With the row-level lock every increment is serialised and the final
   counter equals exactly 20.

2. Hard-limit boundary:
   When 10 concurrent tasks race against a ``daily_limit=5`` quota, the lock
   guarantees that exactly 5 succeed (not 6 or more) and ``events_today==5``.

Each test provisions its own tenant and deletes the row on teardown.
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from common.exceptions import QuotaExceededError
from common.models.quota import TenantQuota
from common.schemas.quota import QuotaProvision
from services.quota.service import QuotaService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    return uuid4().hex[:8]


async def _provision(engine: AsyncEngine, tenant_id: str, tier: str = "starter") -> None:
    async with AsyncSession(engine) as sess:
        await QuotaService(sess).provision(
            QuotaProvision(tenant_id=tenant_id, subscription_tier=tier)
        )


async def _read_events_today(engine: AsyncEngine, tenant_id: str) -> int:
    async with AsyncSession(engine) as sess:
        result = await sess.execute(
            select(TenantQuota).where(TenantQuota.tenant_id == tenant_id)
        )
        return result.scalar_one().events_today


async def _cleanup(engine: AsyncEngine, tenant_id: str) -> None:
    async with AsyncSession(engine) as sess:
        async with sess.begin():
            await sess.execute(
                delete(TenantQuota).where(TenantQuota.tenant_id == tenant_id)
            )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLostUpdatePrevention:
    """SELECT FOR UPDATE serialises concurrent increments — no counter is dropped."""

    async def test_twenty_concurrent_increments_all_counted(
        self, real_engine: AsyncEngine
    ) -> None:
        tenant = f"conc-lost-update-{_uid()}"
        await _provision(real_engine, tenant)

        async def _increment() -> None:
            async with AsyncSession(real_engine) as sess:
                await QuotaService(sess).check_and_increment(tenant)

        try:
            await asyncio.gather(*[_increment() for _ in range(20)])
            events_today = await _read_events_today(real_engine, tenant)
            assert events_today == 20, (
                f"Expected events_today=20 after 20 concurrent increments,"
                f" got {events_today}"
            )
        finally:
            await _cleanup(real_engine, tenant)


class TestHardLimitBoundary:
    """Concurrent tasks that exceed the quota are rejected — no over-counting."""

    async def test_concurrent_tasks_capped_at_daily_limit(
        self, real_engine: AsyncEngine
    ) -> None:
        tenant = f"conc-boundary-{_uid()}"
        await _provision(real_engine, tenant)

        # Override the limit to a small value so the boundary is easy to hit.
        async with AsyncSession(real_engine) as sess:
            async with sess.begin():
                await sess.execute(
                    update(TenantQuota)
                    .where(TenantQuota.tenant_id == tenant)
                    .values(daily_limit=5, monthly_limit=10_000)
                )

        successes = 0
        failures = 0

        async def _try_increment() -> None:
            nonlocal successes, failures
            try:
                async with AsyncSession(real_engine) as sess:
                    await QuotaService(sess).check_and_increment(tenant)
                successes += 1
            except QuotaExceededError:
                failures += 1

        try:
            await asyncio.gather(*[_try_increment() for _ in range(10)])
            events_today = await _read_events_today(real_engine, tenant)
            assert successes == 5, f"Expected 5 successes, got {successes}"
            assert failures == 5, f"Expected 5 failures, got {failures}"
            assert events_today == 5, f"Expected events_today=5, got {events_today}"
        finally:
            await _cleanup(real_engine, tenant)
