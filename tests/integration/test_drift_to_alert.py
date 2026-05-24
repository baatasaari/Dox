"""Integration: Drift detection → Sentinel alert creation."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from common.models.baseline import AgentBaseline
from common.models.event import EventRecord
from common.models.sentinel import SentinelAlert
from common.schemas.drift import AnalyzeRequest
from common.schemas.enums import SentinelType, Severity
from services.drift.service import DriftDetectionService
from services.sentinel.service import SentinelService


def _make_baseline(
    event_counts: dict[str, int],
    total_events: int,
    tenant_id: str = "tenant-acme",
    agent_id: str = "agent-1",
) -> AgentBaseline:
    return AgentBaseline(
        id=uuid4(),
        tenant_id=tenant_id,
        agent_id=agent_id,
        lookback_hours=24,
        event_counts=event_counts,
        total_events=total_events,
        computed_at=datetime.now(UTC),
        is_active=True,
    )


def _make_record(event_type: str, tenant_id: str = "tenant-acme") -> EventRecord:
    now = datetime.now(UTC)
    return EventRecord(
        id=uuid4(),
        event_id=uuid4(),
        trace_id=uuid4(),
        session_id="sess-1",
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


def _make_drift_session(
    baseline: AgentBaseline | None,
    recent_records: list[EventRecord],
) -> MagicMock:
    """Two execute calls: first for active baseline, second for recent events."""
    baseline_result = MagicMock()
    baseline_result.scalar_one_or_none.return_value = baseline

    recent_result = MagicMock()
    recent_result.scalars.return_value.all.return_value = recent_records

    session = MagicMock()
    session.execute = AsyncMock(side_effect=[baseline_result, recent_result])
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _make_sentinel_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


class TestHighDriftCreatesAlert:
    async def test_high_drift_creates_sentinel_alert(self) -> None:
        # Baseline: all agent_started events
        baseline = _make_baseline({"agent_started": 100}, total_events=100)
        # Recent: all tool_call_blocked — completely different distribution
        recent = [_make_record("tool_call_blocked") for _ in range(10)]

        drift_session = _make_drift_session(baseline, recent)
        sentinel_session = _make_sentinel_session()
        sentinel_svc = SentinelService(session=sentinel_session)  # type: ignore[arg-type]

        drift_svc = DriftDetectionService(
            session=drift_session,  # type: ignore[arg-type]
            sentinel_service=sentinel_svc,
        )

        result = await drift_svc.analyze(
            AnalyzeRequest(tenant_id="tenant-acme", agent_id="agent-1", lookback_hours=1)
        )

        assert result.alert_created is True
        sentinel_session.add.assert_called_once()
        added = sentinel_session.add.call_args[0][0]
        assert isinstance(added, SentinelAlert)
        assert added.sentinel_type == SentinelType.drift

    async def test_high_drift_alert_has_high_severity(self) -> None:
        baseline = _make_baseline({"agent_started": 100}, total_events=100)
        recent = [_make_record("tool_call_blocked") for _ in range(10)]

        drift_session = _make_drift_session(baseline, recent)
        sentinel_session = _make_sentinel_session()
        sentinel_svc = SentinelService(session=sentinel_session)  # type: ignore[arg-type]

        drift_svc = DriftDetectionService(
            session=drift_session,  # type: ignore[arg-type]
            sentinel_service=sentinel_svc,
        )

        await drift_svc.analyze(
            AnalyzeRequest(tenant_id="tenant-acme", agent_id="agent-1", lookback_hours=1)
        )

        added = sentinel_session.add.call_args[0][0]
        assert added.severity == Severity.high

    async def test_alert_contains_score_in_details(self) -> None:
        baseline = _make_baseline({"agent_started": 100}, total_events=100)
        recent = [_make_record("tool_call_blocked") for _ in range(10)]

        drift_session = _make_drift_session(baseline, recent)
        sentinel_session = _make_sentinel_session()
        sentinel_svc = SentinelService(session=sentinel_session)  # type: ignore[arg-type]

        drift_svc = DriftDetectionService(
            session=drift_session,  # type: ignore[arg-type]
            sentinel_service=sentinel_svc,
        )

        await drift_svc.analyze(
            AnalyzeRequest(tenant_id="tenant-acme", agent_id="agent-1", lookback_hours=2)
        )

        added = sentinel_session.add.call_args[0][0]
        assert "score" in added.details
        assert "lookback_hours" in added.details
        assert added.details["lookback_hours"] == 2

    async def test_alert_tenant_and_agent_match_request(self) -> None:
        baseline = _make_baseline(
            {"agent_started": 50}, total_events=50, tenant_id="acme", agent_id="bot-2"
        )
        recent = [_make_record("tool_call_blocked", tenant_id="acme")]

        drift_session = _make_drift_session(baseline, recent)
        sentinel_session = _make_sentinel_session()
        sentinel_svc = SentinelService(session=sentinel_session)  # type: ignore[arg-type]

        drift_svc = DriftDetectionService(
            session=drift_session,  # type: ignore[arg-type]
            sentinel_service=sentinel_svc,
        )

        await drift_svc.analyze(
            AnalyzeRequest(tenant_id="acme", agent_id="bot-2", lookback_hours=1)
        )

        added = sentinel_session.add.call_args[0][0]
        assert added.tenant_id == "acme"
        assert added.agent_id == "bot-2"


class TestMediumDriftCreatesAlert:
    async def test_medium_drift_creates_alert_with_medium_severity(self) -> None:
        # Baseline: 60% agent_started, 40% model_called → medium shift
        baseline = _make_baseline(
            {"agent_started": 60, "model_called": 40}, total_events=100
        )
        # Recent: 85% agent_started, 15% model_called → TVD ~0.25*2 = 0.25 each → ~0.25 total
        # Actually let me compute: |0.60 - 0.85|=0.25, |0.40 - 0.15|=0.25 → tvd=0.5/2=0.25
        # That's "low" severity (0.2-0.4). Let me adjust for medium (0.4-0.6):
        # baseline: 50 agent_started, 50 model_called (50/50)
        # recent: 90 agent_started, 10 model_called (90/10 = 0.9/0.1)
        # tvd = (|0.5-0.9| + |0.5-0.1|) / 2 = (0.4+0.4)/2 = 0.4 → medium
        baseline = _make_baseline(
            {"agent_started": 50, "model_called": 50}, total_events=100
        )
        recent = (
            [_make_record("agent_started") for _ in range(9)]
            + [_make_record("model_called") for _ in range(1)]
        )

        drift_session = _make_drift_session(baseline, recent)
        sentinel_session = _make_sentinel_session()
        sentinel_svc = SentinelService(session=sentinel_session)  # type: ignore[arg-type]

        drift_svc = DriftDetectionService(
            session=drift_session,  # type: ignore[arg-type]
            sentinel_service=sentinel_svc,
        )

        result = await drift_svc.analyze(
            AnalyzeRequest(tenant_id="tenant-acme", agent_id="agent-1", lookback_hours=1)
        )

        assert result.alert_created is True
        added = sentinel_session.add.call_args[0][0]
        assert added.severity == Severity.medium


class TestLowDriftNoAlert:
    async def test_low_drift_no_alert_created(self) -> None:
        # Nearly identical distributions → very low TVD
        baseline = _make_baseline(
            {"agent_started": 100, "model_called": 100}, total_events=200
        )
        recent = (
            [_make_record("agent_started") for _ in range(5)]
            + [_make_record("model_called") for _ in range(5)]
        )

        drift_session = _make_drift_session(baseline, recent)
        sentinel_session = _make_sentinel_session()
        sentinel_svc = SentinelService(session=sentinel_session)  # type: ignore[arg-type]

        drift_svc = DriftDetectionService(
            session=drift_session,  # type: ignore[arg-type]
            sentinel_service=sentinel_svc,
        )

        result = await drift_svc.analyze(
            AnalyzeRequest(tenant_id="tenant-acme", agent_id="agent-1", lookback_hours=1)
        )

        assert result.alert_created is False
        sentinel_session.add.assert_not_called()

    async def test_no_sentinel_service_no_alert_regardless_of_score(self) -> None:
        baseline = _make_baseline({"agent_started": 100}, total_events=100)
        recent = [_make_record("tool_call_blocked") for _ in range(10)]

        drift_session = _make_drift_session(baseline, recent)

        drift_svc = DriftDetectionService(
            session=drift_session,  # type: ignore[arg-type]
            sentinel_service=None,
        )

        result = await drift_svc.analyze(
            AnalyzeRequest(tenant_id="tenant-acme", agent_id="agent-1", lookback_hours=1)
        )

        assert result.alert_created is False

    async def test_no_baseline_no_alert(self) -> None:
        # No active baseline → score=0.0 → no alert
        drift_session = _make_drift_session(None, [])

        sentinel_session = _make_sentinel_session()
        sentinel_svc = SentinelService(session=sentinel_session)  # type: ignore[arg-type]

        drift_svc = DriftDetectionService(
            session=drift_session,  # type: ignore[arg-type]
            sentinel_service=sentinel_svc,
        )

        result = await drift_svc.analyze(
            AnalyzeRequest(tenant_id="tenant-acme", agent_id="agent-1", lookback_hours=1)
        )

        assert result.alert_created is False
        sentinel_session.add.assert_not_called()

    async def test_report_has_correct_score_for_high_drift(self) -> None:
        baseline = _make_baseline({"agent_started": 100}, total_events=100)
        recent = [_make_record("tool_call_blocked") for _ in range(10)]

        drift_session = _make_drift_session(baseline, recent)
        sentinel_svc = SentinelService(
            session=_make_sentinel_session()  # type: ignore[arg-type]
        )

        drift_svc = DriftDetectionService(
            session=drift_session,  # type: ignore[arg-type]
            sentinel_service=sentinel_svc,
        )

        result = await drift_svc.analyze(
            AnalyzeRequest(tenant_id="tenant-acme", agent_id="agent-1", lookback_hours=1)
        )

        # TVD between [1.0, 0.0] and [0.0, 1.0] = 1.0
        assert result.drift_score.score == 1.0
        assert result.drift_score.severity == "high"
