"""Quota enforcement service — per-tenant event rate limiting."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import QuotaExceededError
from common.models.quota import TenantQuota
from common.schemas.enums import SubscriptionTier
from common.schemas.quota import QuotaProvision, QuotaStatus

# ---------------------------------------------------------------------------
# Tier-based defaults
# ---------------------------------------------------------------------------

_TIER_LIMITS: dict[str, tuple[int, int]] = {
    SubscriptionTier.starter: (1_000, 20_000),
    SubscriptionTier.professional: (10_000, 200_000),
    SubscriptionTier.enterprise: (100_000, 5_000_000),
}


def _limits_for_tier(tier: str) -> tuple[int, int]:
    """Return (daily_limit, monthly_limit) for *tier*."""
    return _TIER_LIMITS.get(tier, _TIER_LIMITS[SubscriptionTier.starter])


class QuotaService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Provisioning
    # ------------------------------------------------------------------

    async def provision(self, create: QuotaProvision) -> TenantQuota:
        """Create or update the quota record for a tenant."""
        result = await self._session.execute(
            select(TenantQuota).where(TenantQuota.tenant_id == create.tenant_id)
        )
        quota = result.scalar_one_or_none()
        daily, monthly = _limits_for_tier(create.subscription_tier)

        if quota is None:
            quota = TenantQuota(
                id=uuid4(),
                tenant_id=create.tenant_id,
                subscription_tier=create.subscription_tier,
                daily_limit=daily,
                monthly_limit=monthly,
            )
            self._session.add(quota)
        else:
            quota.subscription_tier = create.subscription_tier
            quota.daily_limit = daily
            quota.monthly_limit = monthly

        await self._session.commit()
        return quota

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    async def get_status(self, tenant_id: str) -> QuotaStatus:
        quota = await self._get_or_create(tenant_id)
        self._maybe_reset_windows(quota)
        await self._session.commit()
        return self._to_status(quota)

    # ------------------------------------------------------------------
    # Enforcement
    # ------------------------------------------------------------------

    async def check_and_increment(self, tenant_id: str) -> None:
        """Raise ``QuotaExceededError`` if the tenant is over limit; otherwise count the event."""
        quota = await self._get_or_create(tenant_id)
        self._maybe_reset_windows(quota)

        if quota.events_today >= quota.daily_limit:
            raise QuotaExceededError(
                f"Daily event limit of {quota.daily_limit:,} reached for tenant {tenant_id!r}"
            )
        if quota.events_this_month >= quota.monthly_limit:
            raise QuotaExceededError(
                f"Monthly event limit of {quota.monthly_limit:,} reached for tenant {tenant_id!r}"
            )

        quota.events_today += 1
        quota.events_this_month += 1
        await self._session.commit()

    # ------------------------------------------------------------------
    # Admin reset
    # ------------------------------------------------------------------

    async def reset_daily(self, tenant_id: str) -> QuotaStatus:
        quota = await self._get_or_create(tenant_id)
        quota.events_today = 0
        quota.day_window_start = datetime.now(UTC)
        await self._session.commit()
        return self._to_status(quota)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_or_create(self, tenant_id: str) -> TenantQuota:
        result = await self._session.execute(
            select(TenantQuota).where(TenantQuota.tenant_id == tenant_id)
        )
        quota = result.scalar_one_or_none()
        if quota is None:
            daily, monthly = _limits_for_tier(SubscriptionTier.starter)
            quota = TenantQuota(
                id=uuid4(),
                tenant_id=tenant_id,
                subscription_tier=SubscriptionTier.starter,
                daily_limit=daily,
                monthly_limit=monthly,
            )
            self._session.add(quota)
            await self._session.commit()
        return quota

    @staticmethod
    def _maybe_reset_windows(quota: TenantQuota) -> None:
        now = datetime.now(UTC)
        if quota.day_window_start.date() < now.date():
            quota.events_today = 0
            quota.day_window_start = now
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if quota.month_window_start < month_start:
            quota.events_this_month = 0
            quota.month_window_start = now

    @staticmethod
    def _to_status(quota: TenantQuota) -> QuotaStatus:
        return QuotaStatus(
            tenant_id=quota.tenant_id,
            subscription_tier=quota.subscription_tier,
            daily_limit=quota.daily_limit,
            monthly_limit=quota.monthly_limit,
            events_today=quota.events_today,
            events_this_month=quota.events_this_month,
            daily_remaining=max(0, quota.daily_limit - quota.events_today),
            monthly_remaining=max(0, quota.monthly_limit - quota.events_this_month),
            is_over_daily_limit=quota.events_today >= quota.daily_limit,
            is_over_monthly_limit=quota.events_this_month >= quota.monthly_limit,
            day_window_start=quota.day_window_start,
            month_window_start=quota.month_window_start,
        )
