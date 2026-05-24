"""Integration: ComplianceService cross-module aggregation."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from common.models.event import EventRecord
from common.models.policy import Policy
from common.models.sentinel import SentinelAlert
from common.schemas.enums import SentinelType, Severity, SubscriptionTier
from common.schemas.quota import QuotaStatus
from services.compliance.service import ComplianceService
from services.quota.service import QuotaService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(event_type: str) -> EventRecord:
    now = datetime.now(UTC)
    return EventRecord(
        id=uuid4(),
        event_id=uuid4(),
        trace_id=uuid4(),
        session_id="s1",
        tenant_id="acme",
        agent_id="agent-1",
        agent_version="1.0",
        event_type=event_type,
        environment="prod",
        timestamp=now,
        client_timestamp=now,
        schema_version="1.0",
        payload={},
        raw_event={},
        payload_hash="b" * 64,
    )


def _make_alert(
    severity: str = Severity.high,
    sentinel_type: str = SentinelType.tool_misuse,
    is_resolved: bool = False,
) -> SentinelAlert:
    return SentinelAlert(
        id=uuid4(),
        tenant_id="acme",
        agent_id="agent-1",
        sentinel_type=sentinel_type,
        severity=severity,
        message="alert",
        is_resolved=is_resolved,
    )


def _make_policy() -> Policy:
    return Policy(
        id=uuid4(),
        tenant_id="acme",
        name="p",
        sentinel_type=SentinelType.tool_misuse,
        severity=Severity.high,
        action="block_tool_call",
    )


def _quota_status(
    tier: str = SubscriptionTier.starter,
    daily_remaining: int = 800,
    monthly_remaining: int = 16000,
) -> QuotaStatus:
    now = datetime.now(UTC)
    return QuotaStatus(
        tenant_id="acme",
        subscription_tier=tier,
        daily_limit=1000,
        monthly_limit=20000,
        events_today=200,
        events_this_month=4000,
        daily_remaining=daily_remaining,
        monthly_remaining=monthly_remaining,
        is_over_daily_limit=daily_remaining == 0,
        is_over_monthly_limit=monthly_remaining == 0,
        day_window_start=now,
        month_window_start=now,
    )


def _make_session(
    events: list[EventRecord],
    alerts: list[SentinelAlert],
    policies: list[Policy],
) -> MagicMock:
    ev_r = MagicMock()
    ev_r.scalars.return_value.all.return_value = events
    al_r = MagicMock()
    al_r.scalars.return_value.all.return_value = alerts
    pol_r = MagicMock()
    pol_r.scalars.return_value.all.return_value = policies
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[ev_r, al_r, pol_r])
    return session


def _make_quota_svc(status: QuotaStatus) -> MagicMock:
    svc = MagicMock(spec=QuotaService)
    svc.get_status = AsyncMock(return_value=status)
    return svc


# ---------------------------------------------------------------------------
# Full report generation
# ---------------------------------------------------------------------------


class TestFullReportGeneration:
    async def test_empty_tenant_report_has_all_zeros(self) -> None:
        session = _make_session([], [], [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_quota_status()),
        )
        report = await svc.generate_report("acme")

        assert report.events.total_count == 0
        assert report.events.by_type == {}
        assert report.alerts.total_count == 0
        assert report.alerts.unresolved_count == 0
        assert report.policies.active_count == 0

    async def test_event_types_aggregated_correctly(self) -> None:
        events = (
            [_make_event("agent_started")] * 3
            + [_make_event("tool_call_blocked")] * 2
            + [_make_event("model_called")] * 5
        )
        session = _make_session(events, [], [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_quota_status()),
        )
        report = await svc.generate_report("acme")

        assert report.events.total_count == 10
        assert report.events.by_type["agent_started"] == 3
        assert report.events.by_type["tool_call_blocked"] == 2
        assert report.events.by_type["model_called"] == 5

    async def test_alert_severity_distribution(self) -> None:
        alerts = (
            [_make_alert(severity=Severity.critical)] * 1
            + [_make_alert(severity=Severity.high)] * 3
            + [_make_alert(severity=Severity.medium)] * 2
        )
        session = _make_session([], alerts, [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_quota_status()),
        )
        report = await svc.generate_report("acme")

        assert report.alerts.total_count == 6
        assert report.alerts.by_severity["critical"] == 1
        assert report.alerts.by_severity["high"] == 3
        assert report.alerts.by_severity["medium"] == 2

    async def test_unresolved_vs_resolved_split(self) -> None:
        alerts = [
            _make_alert(is_resolved=False),
            _make_alert(is_resolved=False),
            _make_alert(is_resolved=False),
            _make_alert(is_resolved=True),
            _make_alert(is_resolved=True),
        ]
        session = _make_session([], alerts, [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_quota_status()),
        )
        report = await svc.generate_report("acme")

        assert report.alerts.total_count == 5
        assert report.alerts.unresolved_count == 3

    async def test_multiple_sentinel_types_in_alert_summary(self) -> None:
        alerts = [
            _make_alert(sentinel_type=SentinelType.drift),
            _make_alert(sentinel_type=SentinelType.drift),
            _make_alert(sentinel_type=SentinelType.injection),
        ]
        session = _make_session([], alerts, [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_quota_status()),
        )
        report = await svc.generate_report("acme")

        assert report.alerts.by_type["drift"] == 2
        assert report.alerts.by_type["injection"] == 1

    async def test_policy_count_reflects_active_policies(self) -> None:
        policies = [_make_policy() for _ in range(7)]
        session = _make_session([], [], policies)
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_quota_status()),
        )
        report = await svc.generate_report("acme")
        assert report.policies.active_count == 7

    async def test_quota_over_daily_limit_reflected(self) -> None:
        session = _make_session([], [], [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(
                _quota_status(daily_remaining=0, monthly_remaining=5000)
            ),
        )
        report = await svc.generate_report("acme")
        assert report.quota.is_over_daily_limit is True
        assert report.quota.is_over_monthly_limit is False

    async def test_quota_tier_enterprise(self) -> None:
        session = _make_session([], [], [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(
                _quota_status(tier=SubscriptionTier.enterprise, daily_remaining=99_000)
            ),
        )
        report = await svc.generate_report("acme")
        assert report.quota.subscription_tier == "enterprise"
        assert report.quota.daily_remaining == 99_000

    async def test_lookback_hours_in_event_summary_matches_request(self) -> None:
        session = _make_session([], [], [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_quota_status()),
        )
        report = await svc.generate_report("acme", lookback_hours=168)
        assert report.lookback_hours == 168
        assert report.events.lookback_hours == 168
