"""Integration: QuotaService business logic with real model instances."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common.exceptions import QuotaExceededError
from common.models.quota import TenantQuota
from common.schemas.enums import SubscriptionTier
from common.schemas.quota import QuotaProvision
from services.quota.service import QuotaService


def _make_quota(
    *,
    tenant_id: str = "tenant-acme",
    subscription_tier: str = SubscriptionTier.starter,
    daily_limit: int = 10,
    monthly_limit: int = 100,
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


def _session_returning(quota: TenantQuota | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = quota
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


class TestQuotaAutoProvision:
    async def test_auto_provisions_new_tenant_on_check(self) -> None:
        session = _session_returning(None)
        svc = QuotaService(session)  # type: ignore[arg-type]

        await svc.check_and_increment("brand-new-tenant")

        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert isinstance(added, TenantQuota)
        assert added.tenant_id == "brand-new-tenant"
        assert added.subscription_tier == SubscriptionTier.starter

    async def test_new_tenant_gets_starter_limits(self) -> None:
        session = _session_returning(None)
        svc = QuotaService(session)  # type: ignore[arg-type]

        await svc.check_and_increment("new-tenant")

        added = session.add.call_args[0][0]
        assert added.daily_limit == 1_000
        assert added.monthly_limit == 20_000

    async def test_provision_creates_professional_quota(self) -> None:
        session = _session_returning(None)
        svc = QuotaService(session)  # type: ignore[arg-type]

        quota = await svc.provision(
            QuotaProvision(
                tenant_id="acme", subscription_tier=SubscriptionTier.professional
            )
        )

        assert quota.daily_limit == 10_000
        assert quota.monthly_limit == 200_000
        session.add.assert_called_once()

    async def test_provision_updates_existing_quota(self) -> None:
        existing = _make_quota(subscription_tier=SubscriptionTier.starter)
        session = _session_returning(existing)
        svc = QuotaService(session)  # type: ignore[arg-type]

        result = await svc.provision(
            QuotaProvision(
                tenant_id="tenant-acme",
                subscription_tier=SubscriptionTier.enterprise,
            )
        )

        assert result.subscription_tier == SubscriptionTier.enterprise
        assert result.daily_limit == 100_000
        session.add.assert_not_called()


class TestQuotaIncrementLogic:
    async def test_increments_both_counters(self) -> None:
        quota = _make_quota(events_today=5, events_this_month=50)
        session = _session_returning(quota)
        svc = QuotaService(session)  # type: ignore[arg-type]

        await svc.check_and_increment("tenant-acme")

        assert quota.events_today == 6
        assert quota.events_this_month == 51

    async def test_commits_after_increment(self) -> None:
        quota = _make_quota()
        session = _session_returning(quota)
        svc = QuotaService(session)  # type: ignore[arg-type]

        await svc.check_and_increment("tenant-acme")

        session.commit.assert_awaited()

    async def test_sequential_increments_accumulate(self) -> None:
        quota = _make_quota(daily_limit=100, monthly_limit=1000)
        results = [MagicMock() for _ in range(5)]
        for r in results:
            r.scalar_one_or_none.return_value = quota
        session = MagicMock()
        session.execute = AsyncMock(side_effect=results)
        session.add = MagicMock()
        session.commit = AsyncMock()
        svc = QuotaService(session)  # type: ignore[arg-type]

        for _ in range(5):
            await svc.check_and_increment("tenant-acme")

        assert quota.events_today == 5
        assert quota.events_this_month == 5


class TestQuotaLimitEnforcement:
    async def test_daily_limit_raises_quota_exceeded(self) -> None:
        quota = _make_quota(daily_limit=10, events_today=10)
        session = _session_returning(quota)
        svc = QuotaService(session)  # type: ignore[arg-type]

        with pytest.raises(QuotaExceededError):
            await svc.check_and_increment("tenant-acme")

    async def test_monthly_limit_raises_quota_exceeded(self) -> None:
        quota = _make_quota(monthly_limit=100, events_this_month=100)
        session = _session_returning(quota)
        svc = QuotaService(session)  # type: ignore[arg-type]

        with pytest.raises(QuotaExceededError):
            await svc.check_and_increment("tenant-acme")

    async def test_daily_limit_blocks_even_with_monthly_headroom(self) -> None:
        quota = _make_quota(
            daily_limit=10, events_today=10,
            monthly_limit=1000, events_this_month=5,
        )
        session = _session_returning(quota)
        svc = QuotaService(session)  # type: ignore[arg-type]

        with pytest.raises(QuotaExceededError):
            await svc.check_and_increment("tenant-acme")

    async def test_monthly_limit_blocks_even_with_daily_headroom(self) -> None:
        quota = _make_quota(
            daily_limit=100, events_today=0,
            monthly_limit=100, events_this_month=100,
        )
        session = _session_returning(quota)
        svc = QuotaService(session)  # type: ignore[arg-type]

        with pytest.raises(QuotaExceededError):
            await svc.check_and_increment("tenant-acme")

    async def test_one_below_limit_succeeds(self) -> None:
        quota = _make_quota(daily_limit=10, events_today=9)
        session = _session_returning(quota)
        svc = QuotaService(session)  # type: ignore[arg-type]

        await svc.check_and_increment("tenant-acme")

        assert quota.events_today == 10


class TestDailyReset:
    async def test_reset_daily_clears_events_today(self) -> None:
        quota = _make_quota(events_today=999)
        session = _session_returning(quota)
        svc = QuotaService(session)  # type: ignore[arg-type]

        status = await svc.reset_daily("tenant-acme")

        assert status.events_today == 0
        session.commit.assert_awaited()

    async def test_reset_daily_preserves_monthly_count(self) -> None:
        quota = _make_quota(events_today=500, events_this_month=3000)
        session = _session_returning(quota)
        svc = QuotaService(session)  # type: ignore[arg-type]

        status = await svc.reset_daily("tenant-acme")

        assert status.events_this_month == 3000

    async def test_reset_daily_allows_subsequent_increment(self) -> None:
        quota = _make_quota(daily_limit=5, events_today=5)
        results = [
            MagicMock(),  # for reset_daily
            MagicMock(),  # for check_and_increment
        ]
        results[0].scalar_one_or_none.return_value = quota
        results[1].scalar_one_or_none.return_value = quota
        session = MagicMock()
        session.execute = AsyncMock(side_effect=results)
        session.add = MagicMock()
        session.commit = AsyncMock()
        svc = QuotaService(session)  # type: ignore[arg-type]

        await svc.reset_daily("tenant-acme")
        assert quota.events_today == 0

        # Now should succeed (events_today reset to 0, below daily_limit=5)
        await svc.check_and_increment("tenant-acme")
        assert quota.events_today == 1


class TestWindowReset:
    async def test_expired_day_window_resets_counter_before_check(self) -> None:
        yesterday = datetime.now(UTC) - timedelta(days=2)
        quota = _make_quota(
            daily_limit=5,
            events_today=5,  # at limit — but window expired
            day_window_start=yesterday,
        )
        session = _session_returning(quota)
        svc = QuotaService(session)  # type: ignore[arg-type]

        # Window has expired so events_today should reset to 0 before limit check
        await svc.check_and_increment("tenant-acme")
        # After reset + increment: events_today == 1, not raising
        assert quota.events_today == 1

    async def test_expired_month_window_resets_counter_before_check(self) -> None:
        last_month = datetime.now(UTC).replace(day=1) - timedelta(days=1)
        quota = _make_quota(
            monthly_limit=5,
            events_this_month=5,  # at limit — but window expired
            month_window_start=last_month,
        )
        session = _session_returning(quota)
        svc = QuotaService(session)  # type: ignore[arg-type]

        await svc.check_and_increment("tenant-acme")
        assert quota.events_this_month == 1


class TestStatusReport:
    async def test_get_status_computes_remaining(self) -> None:
        quota = _make_quota(daily_limit=100, events_today=30)
        session = _session_returning(quota)
        svc = QuotaService(session)  # type: ignore[arg-type]

        status = await svc.get_status("tenant-acme")

        assert status.daily_remaining == 70
        assert status.is_over_daily_limit is False

    async def test_get_status_remaining_never_negative(self) -> None:
        quota = _make_quota(daily_limit=10, events_today=15)
        session = _session_returning(quota)
        svc = QuotaService(session)  # type: ignore[arg-type]

        status = await svc.get_status("tenant-acme")

        assert status.daily_remaining == 0
        assert status.is_over_daily_limit is True

    async def test_get_status_for_new_tenant_auto_provisions(self) -> None:
        session = _session_returning(None)
        svc = QuotaService(session)  # type: ignore[arg-type]

        status = await svc.get_status("new-tenant")

        assert status.subscription_tier == SubscriptionTier.starter
        assert status.daily_remaining == 1_000
