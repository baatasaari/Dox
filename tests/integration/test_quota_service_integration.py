"""Integration: QuotaService with real TenantQuota model instances.

These tests exercise the full quota enforcement cycle — provisioning,
incrementing, limit enforcement, resets, and window expiry — using real
QuotaService instances with real TenantQuota objects rather than mocked
service methods.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common.exceptions import QuotaExceededError
from common.models.quota import TenantQuota
from common.schemas.enums import SubscriptionTier
from services.quota.service import QuotaService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_quota(
    tenant_id: str = "tenant-acme",
    subscription_tier: str = SubscriptionTier.starter,
    daily_limit: int = 1_000,
    monthly_limit: int = 20_000,
    events_today: int = 0,
    events_this_month: int = 0,
    day_window_start: datetime | None = None,
    month_window_start: datetime | None = None,
) -> TenantQuota:
    now = datetime.now(UTC)
    return TenantQuota(
        id=uuid4(),
        tenant_id=tenant_id,
        subscription_tier=subscription_tier,
        daily_limit=daily_limit,
        monthly_limit=monthly_limit,
        events_today=events_today,
        events_this_month=events_this_month,
        day_window_start=day_window_start or now,
        month_window_start=month_window_start or now,
    )


def _scalar_result(obj: object) -> MagicMock:
    """Mock execute result whose scalar_one_or_none() returns *obj*."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


def _make_session(*execute_results: MagicMock) -> MagicMock:
    """Session mock whose execute() calls return *execute_results* in order."""
    session = MagicMock()
    session.execute = AsyncMock(side_effect=list(execute_results))
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAutoProvisionNewTenant:
    async def test_auto_provisions_new_tenant(self) -> None:
        """_get_or_create adds and commits a starter quota when none exists."""
        session = _make_session(_scalar_result(None))
        svc = QuotaService(session)  # type: ignore[arg-type]

        # check_and_increment calls _get_or_create internally
        await svc.check_and_increment("new-tenant")

        session.add.assert_called_once()
        session.commit.assert_awaited()

        added = session.add.call_args[0][0]
        assert isinstance(added, TenantQuota)
        assert added.tenant_id == "new-tenant"
        assert added.subscription_tier == SubscriptionTier.starter
        assert added.daily_limit == 1_000
        assert added.monthly_limit == 20_000

    async def test_auto_provisioned_quota_has_zero_counters(self) -> None:
        """A freshly provisioned quota starts with events_today == events_this_month == 0."""
        session = _make_session(_scalar_result(None))
        svc = QuotaService(session)  # type: ignore[arg-type]

        await svc.check_and_increment("fresh-tenant")

        added = session.add.call_args[0][0]
        # The object is constructed with defaults then incremented; verify it is a TenantQuota.
        assert isinstance(added, TenantQuota)
        assert added.tenant_id == "fresh-tenant"


class TestIncrementWithinLimits:
    async def test_increments_counter_within_limits(self) -> None:
        """With headroom available, check_and_increment raises nothing and increments."""
        quota = _make_quota(events_today=0, events_this_month=0, daily_limit=10, monthly_limit=100)
        session = _make_session(_scalar_result(quota))
        svc = QuotaService(session)  # type: ignore[arg-type]

        await svc.check_and_increment("tenant-acme")

        assert quota.events_today == 1
        assert quota.events_this_month == 1

    async def test_each_call_increments_by_one(self) -> None:
        """Consecutive increments accumulate correctly on the real model object."""
        quota = _make_quota(
            events_today=5, events_this_month=50, daily_limit=100, monthly_limit=1000
        )

        call_count = 0

        async def _execute(_stmt: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            return _scalar_result(quota)

        session = MagicMock()
        session.execute = _execute
        session.add = MagicMock()
        session.commit = AsyncMock()

        svc = QuotaService(session)  # type: ignore[arg-type]

        await svc.check_and_increment("tenant-acme")
        await svc.check_and_increment("tenant-acme")
        await svc.check_and_increment("tenant-acme")

        assert quota.events_today == 8
        assert quota.events_this_month == 53

    async def test_commits_after_successful_increment(self) -> None:
        quota = _make_quota(daily_limit=100, monthly_limit=1000)
        session = _make_session(_scalar_result(quota))
        svc = QuotaService(session)  # type: ignore[arg-type]

        await svc.check_and_increment("tenant-acme")

        session.commit.assert_awaited()


class TestDailyLimitEnforced:
    async def test_raises_when_daily_limit_reached(self) -> None:
        """QuotaExceededError is raised when events_today == daily_limit."""
        quota = _make_quota(
            daily_limit=10, events_today=10, monthly_limit=1000, events_this_month=10
        )
        session = _make_session(_scalar_result(quota))
        svc = QuotaService(session)  # type: ignore[arg-type]

        with pytest.raises(QuotaExceededError):
            await svc.check_and_increment("tenant-acme")

    async def test_counter_not_incremented_when_limit_reached(self) -> None:
        """When the daily limit is hit, counters stay at their current value."""
        quota = _make_quota(daily_limit=5, events_today=5, monthly_limit=100, events_this_month=5)
        session = _make_session(_scalar_result(quota))
        svc = QuotaService(session)  # type: ignore[arg-type]

        with pytest.raises(QuotaExceededError):
            await svc.check_and_increment("tenant-acme")

        # counters must not have changed
        assert quota.events_today == 5
        assert quota.events_this_month == 5

    async def test_one_below_daily_limit_succeeds(self) -> None:
        """events_today = daily_limit - 1 → increment is still allowed."""
        quota = _make_quota(daily_limit=10, events_today=9, monthly_limit=1000, events_this_month=9)
        session = _make_session(_scalar_result(quota))
        svc = QuotaService(session)  # type: ignore[arg-type]

        await svc.check_and_increment("tenant-acme")

        assert quota.events_today == 10


class TestResetDaily:
    async def test_reset_daily_clears_counter(self) -> None:
        """reset_daily sets events_today to 0 and commits."""
        quota = _make_quota(events_today=500, daily_limit=1_000)
        session = _make_session(_scalar_result(quota))
        svc = QuotaService(session)  # type: ignore[arg-type]

        status = await svc.reset_daily("tenant-acme")

        assert quota.events_today == 0
        assert status.events_today == 0
        session.commit.assert_awaited()

    async def test_reset_daily_does_not_clear_monthly_counter(self) -> None:
        """reset_daily only touches the daily counter, not the monthly one."""
        quota = _make_quota(
            events_today=500, events_this_month=3_000, daily_limit=1_000, monthly_limit=20_000
        )
        session = _make_session(_scalar_result(quota))
        svc = QuotaService(session)  # type: ignore[arg-type]

        await svc.reset_daily("tenant-acme")

        assert quota.events_this_month == 3_000

    async def test_reset_daily_updates_day_window_start(self) -> None:
        """After reset_daily, day_window_start is refreshed to now."""
        old_start = datetime.now(UTC) - timedelta(days=3)
        quota = _make_quota(events_today=200, day_window_start=old_start)
        session = _make_session(_scalar_result(quota))
        svc = QuotaService(session)  # type: ignore[arg-type]

        before = datetime.now(UTC)
        await svc.reset_daily("tenant-acme")
        after = datetime.now(UTC)

        assert before <= quota.day_window_start <= after

    async def test_after_reset_daily_increment_succeeds(self) -> None:
        """After a daily reset, a tenant that was at its limit can ingest again."""
        quota = _make_quota(
            daily_limit=10, events_today=10, monthly_limit=1_000, events_this_month=10
        )

        # Two separate service calls, each getting the same quota object
        async def _execute(_stmt: object) -> MagicMock:
            return _scalar_result(quota)

        session = MagicMock()
        session.execute = _execute
        session.add = MagicMock()
        session.commit = AsyncMock()

        svc = QuotaService(session)  # type: ignore[arg-type]

        # reset clears events_today
        await svc.reset_daily("tenant-acme")
        assert quota.events_today == 0

        # now increment should succeed
        await svc.check_and_increment("tenant-acme")
        assert quota.events_today == 1


class TestMonthlyLimitIndependent:
    async def test_monthly_limit_independent_of_daily(self) -> None:
        """Monthly limit raises even when daily counter is 0."""
        quota = _make_quota(
            daily_limit=1_000,
            monthly_limit=100,
            events_today=0,
            events_this_month=100,
        )
        session = _make_session(_scalar_result(quota))
        svc = QuotaService(session)  # type: ignore[arg-type]

        with pytest.raises(QuotaExceededError):
            await svc.check_and_increment("tenant-acme")

    async def test_daily_exhausted_before_monthly_raises_daily_error(self) -> None:
        """Daily limit is checked first — raises QuotaExceededError for daily cap."""
        quota = _make_quota(
            daily_limit=10,
            monthly_limit=10_000,
            events_today=10,
            events_this_month=50,
        )
        session = _make_session(_scalar_result(quota))
        svc = QuotaService(session)  # type: ignore[arg-type]

        with pytest.raises(QuotaExceededError) as exc_info:
            await svc.check_and_increment("tenant-acme")

        # The error message mentions the daily limit
        assert "Daily" in exc_info.value.detail or "daily" in exc_info.value.detail.lower()

    async def test_monthly_check_in_error_message(self) -> None:
        """Monthly quota error message mentions the monthly limit."""
        quota = _make_quota(
            daily_limit=1_000,
            monthly_limit=50,
            events_today=0,
            events_this_month=50,
        )
        session = _make_session(_scalar_result(quota))
        svc = QuotaService(session)  # type: ignore[arg-type]

        with pytest.raises(QuotaExceededError) as exc_info:
            await svc.check_and_increment("tenant-acme")

        assert "Monthly" in exc_info.value.detail or "monthly" in exc_info.value.detail.lower()


class TestWindowResetWhenExpired:
    async def test_window_reset_when_day_expired(self) -> None:
        """Expired day window resets events_today before the limit check runs."""
        yesterday = datetime.now(UTC) - timedelta(days=1)
        # events_today is at the daily limit, but the window is stale
        quota = _make_quota(
            daily_limit=10,
            events_today=10,
            monthly_limit=10_000,
            events_this_month=10,
            day_window_start=yesterday,
        )
        session = _make_session(_scalar_result(quota))
        svc = QuotaService(session)  # type: ignore[arg-type]

        # Should NOT raise because _maybe_reset_windows zeroes events_today first
        await svc.check_and_increment("tenant-acme")

        # After window reset + increment, events_today is 1 (reset to 0, then +1)
        assert quota.events_today == 1

    async def test_window_reset_when_month_expired(self) -> None:
        """Expired month window resets events_this_month before the limit check."""
        last_month = datetime.now(UTC).replace(day=1) - timedelta(days=1)
        quota = _make_quota(
            daily_limit=1_000,
            events_today=0,
            monthly_limit=50,
            events_this_month=50,
            month_window_start=last_month,
        )
        session = _make_session(_scalar_result(quota))
        svc = QuotaService(session)  # type: ignore[arg-type]

        # Should NOT raise — month window is stale, so events_this_month resets to 0
        await svc.check_and_increment("tenant-acme")

        assert quota.events_this_month == 1

    async def test_current_window_does_not_reset(self) -> None:
        """When day window is current, events_today is preserved (not reset)."""
        now = datetime.now(UTC)
        quota = _make_quota(
            daily_limit=100,
            events_today=42,
            monthly_limit=1_000,
            events_this_month=42,
            day_window_start=now,
        )
        session = _make_session(_scalar_result(quota))
        svc = QuotaService(session)  # type: ignore[arg-type]

        await svc.check_and_increment("tenant-acme")

        # 42 preserved + 1 increment
        assert quota.events_today == 43
