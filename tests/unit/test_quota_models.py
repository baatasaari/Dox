"""Module 9 — Quota: model tests."""
from __future__ import annotations

from uuid import uuid4

from common.models.quota import TenantQuota


def _make_quota(**kw: object) -> TenantQuota:
    defaults = dict(
        id=uuid4(),
        tenant_id="tenant-acme",
        subscription_tier="starter",
        daily_limit=1_000,
        monthly_limit=20_000,
    )
    defaults.update(kw)
    return TenantQuota(**defaults)


class TestTenantQuotaDefaults:
    def test_events_today_defaults_to_zero(self) -> None:
        q = _make_quota()
        assert q.events_today == 0

    def test_events_this_month_defaults_to_zero(self) -> None:
        q = _make_quota()
        assert q.events_this_month == 0

    def test_day_window_start_is_set(self) -> None:
        q = _make_quota()
        assert q.day_window_start is not None

    def test_month_window_start_is_set(self) -> None:
        q = _make_quota()
        assert q.month_window_start is not None

    def test_explicit_events_today_preserved(self) -> None:
        q = _make_quota(events_today=42)
        assert q.events_today == 42


class TestTenantQuotaFields:
    def test_tenant_id_stored(self) -> None:
        q = _make_quota(tenant_id="tenant-xyz")
        assert q.tenant_id == "tenant-xyz"

    def test_subscription_tier_stored(self) -> None:
        q = _make_quota(subscription_tier="professional")
        assert q.subscription_tier == "professional"

    def test_limits_stored(self) -> None:
        q = _make_quota(daily_limit=500, monthly_limit=10_000)
        assert q.daily_limit == 500
        assert q.monthly_limit == 10_000
