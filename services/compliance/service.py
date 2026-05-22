"""Compliance reporting service — cross-module tenant health summary."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.event import EventRecord
from common.models.policy import Policy
from common.models.sentinel import SentinelAlert
from common.schemas.compliance import (
    AlertSummary,
    ComplianceReport,
    EventSummary,
    PolicySummary,
    QuotaSummary,
)
from services.quota.service import QuotaService


class ComplianceService:
    def __init__(
        self,
        session: AsyncSession,
        quota_service: QuotaService | None = None,
    ) -> None:
        self._session = session
        self._quota_service = quota_service or QuotaService(session)

    async def generate_report(
        self, tenant_id: str, lookback_hours: int = 24
    ) -> ComplianceReport:
        now = datetime.now(UTC)
        since = now - timedelta(hours=lookback_hours)

        event_summary = await self._summarize_events(tenant_id, since, lookback_hours)
        alert_summary = await self._summarize_alerts(tenant_id)
        quota_summary = await self._summarize_quota(tenant_id)
        policy_summary = await self._summarize_policies(tenant_id)

        return ComplianceReport(
            tenant_id=tenant_id,
            generated_at=now,
            lookback_hours=lookback_hours,
            events=event_summary,
            alerts=alert_summary,
            quota=quota_summary,
            policies=policy_summary,
        )

    async def _summarize_events(
        self, tenant_id: str, since: datetime, lookback_hours: int
    ) -> EventSummary:
        result = await self._session.execute(
            select(EventRecord).where(
                and_(
                    EventRecord.tenant_id == tenant_id,
                    EventRecord.timestamp >= since,
                )
            )
        )
        events = list(result.scalars().all())
        by_type: dict[str, int] = {}
        for ev in events:
            by_type[str(ev.event_type)] = by_type.get(str(ev.event_type), 0) + 1
        return EventSummary(
            total_count=len(events),
            by_type=by_type,
            lookback_hours=lookback_hours,
        )

    async def _summarize_alerts(self, tenant_id: str) -> AlertSummary:
        result = await self._session.execute(
            select(SentinelAlert).where(SentinelAlert.tenant_id == tenant_id)
        )
        alerts = list(result.scalars().all())
        by_severity: dict[str, int] = {}
        by_type: dict[str, int] = {}
        unresolved = 0
        for al in alerts:
            sev = str(al.severity)
            stype = str(al.sentinel_type)
            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_type[stype] = by_type.get(stype, 0) + 1
            if not al.is_resolved:
                unresolved += 1
        return AlertSummary(
            total_count=len(alerts),
            unresolved_count=unresolved,
            by_severity=by_severity,
            by_type=by_type,
        )

    async def _summarize_quota(self, tenant_id: str) -> QuotaSummary:
        status = await self._quota_service.get_status(tenant_id)
        return QuotaSummary(
            subscription_tier=str(status.subscription_tier),
            daily_remaining=status.daily_remaining,
            monthly_remaining=status.monthly_remaining,
            is_over_daily_limit=status.is_over_daily_limit,
            is_over_monthly_limit=status.is_over_monthly_limit,
        )

    async def _summarize_policies(self, tenant_id: str) -> PolicySummary:
        result = await self._session.execute(
            select(Policy).where(
                and_(
                    Policy.tenant_id == tenant_id,
                    Policy.is_active.is_(True),
                )
            )
        )
        policies = list(result.scalars().all())
        return PolicySummary(active_count=len(policies))
