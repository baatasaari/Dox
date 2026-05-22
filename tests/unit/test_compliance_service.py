"""Module 13 — Compliance Reporting: service layer tests."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from common.models.event import EventRecord
from common.models.policy import Policy
from common.models.sentinel import SentinelAlert
from common.schemas.compliance import ComplianceReport
from common.schemas.enums import SentinelType, Severity, SubscriptionTier
from common.schemas.quota import QuotaStatus
from services.compliance.service import ComplianceService
from services.quota.service import QuotaService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(event_type: str, tenant_id: str = "acme") -> EventRecord:
    now = datetime.now(UTC)
    return EventRecord(
        id=uuid4(),
        event_id=uuid4(),
        trace_id=uuid4(),
        session_id="s1",
        tenant_id=tenant_id,
        agent_id="agent-1",
        agent_version="1.0",
        event_type=event_type,
        environment="dev",
        timestamp=now,
        client_timestamp=now,
        schema_version="1.0",
        payload={},
        raw_event={},
        payload_hash="a" * 64,
    )


def _make_alert(
    *,
    severity: str = Severity.high,
    sentinel_type: str = SentinelType.tool_misuse,
    is_resolved: bool = False,
    tenant_id: str = "acme",
) -> SentinelAlert:
    return SentinelAlert(
        id=uuid4(),
        tenant_id=tenant_id,
        agent_id="agent-1",
        sentinel_type=sentinel_type,
        severity=severity,
        message="test",
        is_resolved=is_resolved,
    )


def _make_policy(tenant_id: str = "acme") -> Policy:
    return Policy(
        id=uuid4(),
        tenant_id=tenant_id,
        name="block",
        sentinel_type=SentinelType.tool_misuse,
        severity=Severity.high,
        action="block_tool_call",
    )


def _make_quota_status(
    tier: str = SubscriptionTier.starter,
    daily_remaining: int = 900,
    monthly_remaining: int = 18000,
) -> QuotaStatus:
    now = datetime.now(UTC)
    return QuotaStatus(
        tenant_id="acme",
        subscription_tier=tier,
        daily_limit=1000,
        monthly_limit=20000,
        events_today=100,
        events_this_month=2000,
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
# Report structure
# ---------------------------------------------------------------------------


class TestReportStructure:
    async def test_returns_compliance_report(self) -> None:
        session = _make_session([], [], [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_make_quota_status()),
        )
        result = await svc.generate_report("acme")
        assert isinstance(result, ComplianceReport)

    async def test_tenant_id_echoed(self) -> None:
        session = _make_session([], [], [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_make_quota_status()),
        )
        result = await svc.generate_report("my-tenant")
        assert result.tenant_id == "my-tenant"

    async def test_lookback_hours_echoed(self) -> None:
        session = _make_session([], [], [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_make_quota_status()),
        )
        result = await svc.generate_report("acme", lookback_hours=48)
        assert result.lookback_hours == 48

    async def test_generated_at_is_recent(self) -> None:
        before = datetime.now(UTC)
        session = _make_session([], [], [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_make_quota_status()),
        )
        result = await svc.generate_report("acme")
        after = datetime.now(UTC)
        assert before <= result.generated_at <= after


# ---------------------------------------------------------------------------
# Event summary
# ---------------------------------------------------------------------------


class TestEventSummary:
    async def test_empty_events_zero_count(self) -> None:
        session = _make_session([], [], [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_make_quota_status()),
        )
        result = await svc.generate_report("acme")
        assert result.events.total_count == 0
        assert result.events.by_type == {}

    async def test_counts_events_correctly(self) -> None:
        events = [
            _make_event("agent_started"),
            _make_event("agent_started"),
            _make_event("tool_call_blocked"),
        ]
        session = _make_session(events, [], [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_make_quota_status()),
        )
        result = await svc.generate_report("acme")
        assert result.events.total_count == 3
        assert result.events.by_type["agent_started"] == 2
        assert result.events.by_type["tool_call_blocked"] == 1

    async def test_lookback_hours_in_event_summary(self) -> None:
        session = _make_session([], [], [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_make_quota_status()),
        )
        result = await svc.generate_report("acme", lookback_hours=12)
        assert result.events.lookback_hours == 12


# ---------------------------------------------------------------------------
# Alert summary
# ---------------------------------------------------------------------------


class TestAlertSummary:
    async def test_empty_alerts_zero_count(self) -> None:
        session = _make_session([], [], [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_make_quota_status()),
        )
        result = await svc.generate_report("acme")
        assert result.alerts.total_count == 0
        assert result.alerts.unresolved_count == 0

    async def test_counts_total_alerts(self) -> None:
        alerts = [_make_alert() for _ in range(5)]
        session = _make_session([], alerts, [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_make_quota_status()),
        )
        result = await svc.generate_report("acme")
        assert result.alerts.total_count == 5

    async def test_unresolved_count_excludes_resolved(self) -> None:
        alerts = [
            _make_alert(is_resolved=False),
            _make_alert(is_resolved=False),
            _make_alert(is_resolved=True),
        ]
        session = _make_session([], alerts, [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_make_quota_status()),
        )
        result = await svc.generate_report("acme")
        assert result.alerts.unresolved_count == 2

    async def test_by_severity_aggregation(self) -> None:
        alerts = [
            _make_alert(severity=Severity.high),
            _make_alert(severity=Severity.high),
            _make_alert(severity=Severity.medium),
        ]
        session = _make_session([], alerts, [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_make_quota_status()),
        )
        result = await svc.generate_report("acme")
        assert result.alerts.by_severity["high"] == 2
        assert result.alerts.by_severity["medium"] == 1

    async def test_by_type_aggregation(self) -> None:
        alerts = [
            _make_alert(sentinel_type=SentinelType.tool_misuse),
            _make_alert(sentinel_type=SentinelType.drift),
            _make_alert(sentinel_type=SentinelType.drift),
        ]
        session = _make_session([], alerts, [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_make_quota_status()),
        )
        result = await svc.generate_report("acme")
        assert result.alerts.by_type["tool_misuse"] == 1
        assert result.alerts.by_type["drift"] == 2


# ---------------------------------------------------------------------------
# Quota summary
# ---------------------------------------------------------------------------


class TestQuotaSummary:
    async def test_quota_tier_passed_through(self) -> None:
        session = _make_session([], [], [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(
                _make_quota_status(tier=SubscriptionTier.professional)
            ),
        )
        result = await svc.generate_report("acme")
        assert result.quota.subscription_tier == "professional"

    async def test_daily_remaining_passed_through(self) -> None:
        session = _make_session([], [], [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_make_quota_status(daily_remaining=42)),
        )
        result = await svc.generate_report("acme")
        assert result.quota.daily_remaining == 42

    async def test_over_limit_flag_passed_through(self) -> None:
        session = _make_session([], [], [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(
                _make_quota_status(daily_remaining=0, monthly_remaining=100)
            ),
        )
        result = await svc.generate_report("acme")
        assert result.quota.is_over_daily_limit is True
        assert result.quota.is_over_monthly_limit is False


# ---------------------------------------------------------------------------
# Policy summary
# ---------------------------------------------------------------------------


class TestPolicySummary:
    async def test_zero_policies(self) -> None:
        session = _make_session([], [], [])
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_make_quota_status()),
        )
        result = await svc.generate_report("acme")
        assert result.policies.active_count == 0

    async def test_counts_active_policies(self) -> None:
        policies = [_make_policy() for _ in range(4)]
        session = _make_session([], [], policies)
        svc = ComplianceService(
            session,  # type: ignore[arg-type]
            quota_service=_make_quota_svc(_make_quota_status()),
        )
        result = await svc.generate_report("acme")
        assert result.policies.active_count == 4
