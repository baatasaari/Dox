"""Module 9 — Quota: service layer tests."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common.exceptions import QuotaExceededError
from common.models.quota import TenantQuota
from common.schemas.enums import SubscriptionTier
from common.schemas.quota import QuotaProvision
from services.quota.service import QuotaService, _limits_for_tier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_quota(
    tenant_id: str = "tenant-acme",
    subscription_tier: str = "starter",
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
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


def _make_session(*execute_results: MagicMock) -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=list(execute_results))
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLimitsForTier:
    def test_starter_tier(self) -> None:
        daily, monthly = _limits_for_tier(SubscriptionTier.starter)
        assert daily == 1_000
        assert monthly == 20_000

    def test_professional_tier(self) -> None:
        daily, monthly = _limits_for_tier(SubscriptionTier.professional)
        assert daily == 10_000
        assert monthly == 200_000

    def test_enterprise_tier(self) -> None:
        daily, monthly = _limits_for_tier(SubscriptionTier.enterprise)
        assert daily == 100_000
        assert monthly == 5_000_000

    def test_unknown_tier_falls_back_to_starter(self) -> None:
        daily, monthly = _limits_for_tier("unknown_tier")
        assert daily == 1_000
        assert monthly == 20_000


class TestProvision:
    async def test_creates_new_quota(self) -> None:
        session = _make_session(_scalar_result(None))
        service = QuotaService(session)  # type: ignore[arg-type]
        result = await service.provision(
            QuotaProvision(tenant_id="t", subscription_tier=SubscriptionTier.professional)
        )
        assert isinstance(result, TenantQuota)
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    async def test_updates_existing_quota(self) -> None:
        existing = _make_quota(subscription_tier="starter")
        session = _make_session(_scalar_result(existing))
        service = QuotaService(session)  # type: ignore[arg-type]
        result = await service.provision(
            QuotaProvision(tenant_id="t", subscription_tier=SubscriptionTier.enterprise)
        )
        assert result.subscription_tier == SubscriptionTier.enterprise
        assert result.daily_limit == 100_000
        session.add.assert_not_called()

    async def test_new_quota_has_correct_limits(self) -> None:
        session = _make_session(_scalar_result(None))
        service = QuotaService(session)  # type: ignore[arg-type]
        result = await service.provision(
            QuotaProvision(tenant_id="t", subscription_tier=SubscriptionTier.professional)
        )
        assert result.daily_limit == 10_000
        assert result.monthly_limit == 200_000


class TestCheckAndIncrement:
    async def test_within_limits_increments_counters(self) -> None:
        quota = _make_quota(events_today=0, events_this_month=0)
        session = _make_session(_scalar_result(quota))
        service = QuotaService(session)  # type: ignore[arg-type]
        await service.check_and_increment("tenant-acme")
        assert quota.events_today == 1
        assert quota.events_this_month == 1

    async def test_daily_limit_exceeded_raises(self) -> None:
        quota = _make_quota(daily_limit=10, events_today=10)
        session = _make_session(_scalar_result(quota))
        service = QuotaService(session)  # type: ignore[arg-type]
        with pytest.raises(QuotaExceededError):
            await service.check_and_increment("tenant-acme")

    async def test_monthly_limit_exceeded_raises(self) -> None:
        quota = _make_quota(monthly_limit=100, events_this_month=100)
        session = _make_session(_scalar_result(quota))
        service = QuotaService(session)  # type: ignore[arg-type]
        with pytest.raises(QuotaExceededError):
            await service.check_and_increment("tenant-acme")

    async def test_creates_quota_when_missing(self) -> None:
        session = _make_session(_scalar_result(None))
        service = QuotaService(session)  # type: ignore[arg-type]
        await service.check_and_increment("new-tenant")
        session.add.assert_called_once()

    async def test_commits_after_increment(self) -> None:
        quota = _make_quota()
        session = _make_session(_scalar_result(quota))
        service = QuotaService(session)  # type: ignore[arg-type]
        await service.check_and_increment("t")
        session.commit.assert_awaited()


class TestMaybeResetWindows:
    def test_expired_day_window_resets_events_today(self) -> None:
        yesterday = datetime.now(UTC) - timedelta(days=1)
        quota = _make_quota(events_today=500, day_window_start=yesterday)
        QuotaService._maybe_reset_windows(quota)
        assert quota.events_today == 0

    def test_current_day_window_preserves_events_today(self) -> None:
        quota = _make_quota(events_today=500, day_window_start=datetime.now(UTC))
        QuotaService._maybe_reset_windows(quota)
        assert quota.events_today == 500

    def test_expired_month_window_resets_events_this_month(self) -> None:
        last_month = datetime.now(UTC).replace(day=1) - timedelta(days=1)
        quota = _make_quota(events_this_month=1_000, month_window_start=last_month)
        QuotaService._maybe_reset_windows(quota)
        assert quota.events_this_month == 0

    def test_current_month_window_preserves_events_this_month(self) -> None:
        quota = _make_quota(events_this_month=999, month_window_start=datetime.now(UTC))
        QuotaService._maybe_reset_windows(quota)
        assert quota.events_this_month == 999


class TestToStatus:
    def test_remaining_computed_correctly(self) -> None:
        quota = _make_quota(daily_limit=1000, events_today=300)
        status = QuotaService._to_status(quota)
        assert status.daily_remaining == 700

    def test_remaining_never_negative(self) -> None:
        quota = _make_quota(daily_limit=10, events_today=15)
        status = QuotaService._to_status(quota)
        assert status.daily_remaining == 0

    def test_is_over_daily_limit_true_when_at_limit(self) -> None:
        quota = _make_quota(daily_limit=100, events_today=100)
        status = QuotaService._to_status(quota)
        assert status.is_over_daily_limit is True

    def test_is_over_daily_limit_false_when_under(self) -> None:
        quota = _make_quota(daily_limit=100, events_today=99)
        status = QuotaService._to_status(quota)
        assert status.is_over_daily_limit is False

    def test_subscription_tier_in_status(self) -> None:
        quota = _make_quota(subscription_tier="enterprise")
        status = QuotaService._to_status(quota)
        assert status.subscription_tier == "enterprise"


class TestGetStatus:
    async def test_returns_quota_status(self) -> None:
        quota = _make_quota()
        session = _make_session(_scalar_result(quota))
        service = QuotaService(session)  # type: ignore[arg-type]
        status = await service.get_status("tenant-acme")
        assert status.tenant_id == "tenant-acme"

    async def test_creates_quota_when_missing(self) -> None:
        session = _make_session(_scalar_result(None))
        service = QuotaService(session)  # type: ignore[arg-type]
        status = await service.get_status("new-tenant")
        assert status.subscription_tier == SubscriptionTier.starter


class TestResetDaily:
    async def test_resets_events_today_to_zero(self) -> None:
        quota = _make_quota(events_today=999)
        session = _make_session(_scalar_result(quota))
        service = QuotaService(session)  # type: ignore[arg-type]
        status = await service.reset_daily("tenant-acme")
        assert status.events_today == 0

    async def test_commits_after_reset(self) -> None:
        quota = _make_quota()
        session = _make_session(_scalar_result(quota))
        service = QuotaService(session)  # type: ignore[arg-type]
        await service.reset_daily("t")
        session.commit.assert_awaited_once()
