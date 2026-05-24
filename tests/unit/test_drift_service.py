"""Module 7 — Drift: service layer tests."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common.exceptions import NotFoundError
from common.models.baseline import AgentBaseline
from common.models.event import EventRecord
from common.schemas.drift import AnalyzeRequest, BaselineCreate
from common.schemas.validators import compute_payload_hash
from services.drift.service import DriftDetectionService, _score_to_severity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_baseline(
    tenant_id: str = "tenant-acme",
    agent_id: str = "agent-1",
    event_counts: dict | None = None,
    total_events: int = 10,
    is_active: bool = True,
) -> AgentBaseline:
    return AgentBaseline(
        id=uuid4(),
        tenant_id=tenant_id,
        agent_id=agent_id,
        lookback_hours=24,
        event_counts=event_counts or {"agent_started": 10},
        total_events=total_events,
        computed_at=datetime.now(UTC),
        is_active=is_active,
    )


def _make_event_record(event_type: str = "agent_started") -> EventRecord:
    p = {"step": "test"}
    return EventRecord(
        id=uuid4(),
        event_id=uuid4(),
        trace_id=uuid4(),
        session_id="sess-1",
        tenant_id="tenant-acme",
        agent_id="agent-1",
        agent_version="1.0.0",
        event_type=event_type,
        environment="dev",
        timestamp=datetime.now(UTC),
        client_timestamp=datetime.now(UTC),
        schema_version="1.0",
        payload=p,
        raw_event={},
        payload_hash=compute_payload_hash(p),
    )


def _session_returning(*execute_results: MagicMock) -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=list(execute_results))
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _scalar_result(obj: object) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    r.scalars.return_value.all.return_value = []
    return r


def _scalars_result(items: list[object]) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    r.scalar_one_or_none.return_value = None
    return r


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComputeBaseline:
    async def test_adds_and_commits(self) -> None:
        events_result = _scalars_result([_make_event_record()])
        old_result = _scalars_result([])
        session = _session_returning(events_result, old_result)
        service = DriftDetectionService(session)  # type: ignore[arg-type]
        create = BaselineCreate(tenant_id="t", agent_id="a", lookback_hours=24)
        await service.compute_baseline(create)
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    async def test_returns_agent_baseline(self) -> None:
        events_result = _scalars_result([_make_event_record("agent_started")])
        old_result = _scalars_result([])
        session = _session_returning(events_result, old_result)
        service = DriftDetectionService(session)  # type: ignore[arg-type]
        create = BaselineCreate(tenant_id="t", agent_id="a", lookback_hours=24)
        baseline = await service.compute_baseline(create)
        assert isinstance(baseline, AgentBaseline)
        assert baseline.total_events == 1

    async def test_event_counts_populated_from_events(self) -> None:
        events = [
            _make_event_record("agent_started"),
            _make_event_record("agent_started"),
            _make_event_record("tool_call_started"),
        ]
        events_result = _scalars_result(events)
        old_result = _scalars_result([])
        session = _session_returning(events_result, old_result)
        service = DriftDetectionService(session)  # type: ignore[arg-type]
        baseline = await service.compute_baseline(
            BaselineCreate(tenant_id="t", agent_id="a", lookback_hours=24)
        )
        assert baseline.event_counts == {"agent_started": 2, "tool_call_started": 1}

    async def test_deactivates_existing_baselines(self) -> None:
        old_baseline = _make_baseline(is_active=True)
        events_result = _scalars_result([])
        old_result = _scalars_result([old_baseline])
        session = _session_returning(events_result, old_result)
        service = DriftDetectionService(session)  # type: ignore[arg-type]
        await service.compute_baseline(
            BaselineCreate(tenant_id="t", agent_id="a", lookback_hours=24)
        )
        assert old_baseline.is_active is False

    async def test_empty_event_window_total_is_zero(self) -> None:
        events_result = _scalars_result([])
        old_result = _scalars_result([])
        session = _session_returning(events_result, old_result)
        service = DriftDetectionService(session)  # type: ignore[arg-type]
        baseline = await service.compute_baseline(
            BaselineCreate(tenant_id="t", agent_id="a", lookback_hours=1)
        )
        assert baseline.total_events == 0
        assert baseline.event_counts == {}


class TestGetBaseline:
    async def test_returns_baseline_when_found(self) -> None:
        b = _make_baseline()
        session = _session_returning(_scalar_result(b))
        service = DriftDetectionService(session)  # type: ignore[arg-type]
        result = await service.get_baseline(b.id)
        assert result is b

    async def test_raises_not_found_when_missing(self) -> None:
        session = _session_returning(_scalar_result(None))
        service = DriftDetectionService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await service.get_baseline(uuid4())


class TestListBaselines:
    async def test_returns_list(self) -> None:
        baselines = [_make_baseline(), _make_baseline()]
        session = _session_returning(_scalars_result(baselines))
        service = DriftDetectionService(session)  # type: ignore[arg-type]
        result = await service.list_baselines("tenant-acme")
        assert len(result) == 2

    async def test_empty_returns_empty_list(self) -> None:
        session = _session_returning(_scalars_result([]))
        service = DriftDetectionService(session)  # type: ignore[arg-type]
        result = await service.list_baselines("unknown")
        assert result == []


class TestDeactivateBaseline:
    async def test_sets_is_active_false(self) -> None:
        b = _make_baseline(is_active=True)
        session = _session_returning(_scalar_result(b))
        service = DriftDetectionService(session)  # type: ignore[arg-type]
        result = await service.deactivate_baseline(b.id)
        assert result.is_active is False

    async def test_raises_not_found_when_missing(self) -> None:
        session = _session_returning(_scalar_result(None))
        service = DriftDetectionService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await service.deactivate_baseline(uuid4())

    async def test_commits_after_deactivation(self) -> None:
        b = _make_baseline()
        session = _session_returning(_scalar_result(b))
        service = DriftDetectionService(session)  # type: ignore[arg-type]
        await service.deactivate_baseline(b.id)
        session.commit.assert_awaited_once()


class TestComputeTVD:
    def test_identical_distributions_returns_zero(self) -> None:
        counts = {"agent_started": 10, "tool_call_started": 5}
        score, _ = DriftDetectionService._compute_tvd(counts, 15, counts, 15)
        assert score == pytest.approx(0.0, abs=1e-6)

    def test_completely_disjoint_distributions_returns_one(self) -> None:
        baseline = {"agent_started": 10}
        recent = {"tool_call_started": 10}
        score, _ = DriftDetectionService._compute_tvd(baseline, 10, recent, 10)
        assert score == pytest.approx(1.0, abs=1e-6)

    def test_partial_overlap_returns_intermediate_score(self) -> None:
        baseline = {"a": 5, "b": 5}
        recent = {"a": 8, "b": 2}
        score, _ = DriftDetectionService._compute_tvd(baseline, 10, recent, 10)
        assert 0.0 < score < 1.0

    def test_empty_recent_returns_zero(self) -> None:
        baseline = {"agent_started": 10}
        score, deviations = DriftDetectionService._compute_tvd(baseline, 10, {}, 0)
        assert score == 0.0
        assert deviations == []

    def test_empty_baseline_returns_zero(self) -> None:
        score, deviations = DriftDetectionService._compute_tvd({}, 0, {"a": 1}, 1)
        assert score == 0.0
        assert deviations == []

    def test_deviations_list_has_significant_entries(self) -> None:
        baseline = {"agent_started": 10}
        recent = {"tool_call_started": 10}
        _, deviations = DriftDetectionService._compute_tvd(baseline, 10, recent, 10)
        event_types = {d.event_type for d in deviations}
        assert "agent_started" in event_types
        assert "tool_call_started" in event_types

    def test_score_is_bounded_zero_to_one(self) -> None:
        baseline = {"a": 1}
        recent = {"b": 1, "c": 1, "d": 1}
        score, _ = DriftDetectionService._compute_tvd(baseline, 1, recent, 3)
        assert 0.0 <= score <= 1.0

    def test_deviation_delta_equals_abs_freq_diff(self) -> None:
        baseline = {"a": 6, "b": 4}
        recent = {"a": 4, "b": 6}
        _, deviations = DriftDetectionService._compute_tvd(baseline, 10, recent, 10)
        for dev in deviations:
            assert dev.delta == pytest.approx(abs(dev.baseline_freq - dev.recent_freq), abs=1e-4)


class TestScoreToSeverity:
    def test_below_02_is_none(self) -> None:
        assert _score_to_severity(0.0) == "none"
        assert _score_to_severity(0.19) == "none"

    def test_02_to_04_is_low(self) -> None:
        assert _score_to_severity(0.2) == "low"
        assert _score_to_severity(0.39) == "low"

    def test_04_to_06_is_medium(self) -> None:
        assert _score_to_severity(0.4) == "medium"
        assert _score_to_severity(0.59) == "medium"

    def test_06_and_above_is_high(self) -> None:
        assert _score_to_severity(0.6) == "high"
        assert _score_to_severity(1.0) == "high"


class TestAnalyze:
    def _make_analyze_session(
        self,
        baseline: AgentBaseline | None,
        recent_events: list[EventRecord],
    ) -> MagicMock:
        active_baseline_result = _scalar_result(baseline)
        recent_events_result = _scalars_result(recent_events)
        return _session_returning(active_baseline_result, recent_events_result)

    async def test_no_baseline_returns_zero_score(self) -> None:
        session = self._make_analyze_session(None, [])
        service = DriftDetectionService(session)  # type: ignore[arg-type]
        request = AnalyzeRequest(tenant_id="t", agent_id="a", lookback_hours=1)
        report = await service.analyze(request)
        assert report.drift_score.score == 0.0
        assert report.drift_score.severity == "none"
        assert report.baseline_id is None

    async def test_no_baseline_no_alert(self) -> None:
        mock_sentinel = MagicMock()
        mock_sentinel.create_alert = AsyncMock()
        session = self._make_analyze_session(None, [])
        service = DriftDetectionService(session, sentinel_service=mock_sentinel)  # type: ignore[arg-type]
        report = await service.analyze(AnalyzeRequest(tenant_id="t", agent_id="a"))
        assert report.alert_created is False
        mock_sentinel.create_alert.assert_not_awaited()

    async def test_low_drift_no_alert(self) -> None:
        baseline = _make_baseline(
            event_counts={"agent_started": 10}, total_events=10
        )
        recent = [_make_event_record("agent_started") for _ in range(5)]
        mock_sentinel = MagicMock()
        mock_sentinel.create_alert = AsyncMock()
        session = self._make_analyze_session(baseline, recent)
        service = DriftDetectionService(session, sentinel_service=mock_sentinel)  # type: ignore[arg-type]
        report = await service.analyze(AnalyzeRequest(tenant_id="t", agent_id="a"))
        assert report.alert_created is False
        mock_sentinel.create_alert.assert_not_awaited()

    async def test_high_drift_creates_alert(self) -> None:
        baseline = _make_baseline(
            event_counts={"agent_started": 10}, total_events=10
        )
        # completely different events → TVD = 1.0 → high severity
        recent = [_make_event_record("agent_terminated") for _ in range(5)]
        mock_sentinel = MagicMock()
        mock_sentinel.create_alert = AsyncMock(return_value=MagicMock())
        session = self._make_analyze_session(baseline, recent)
        service = DriftDetectionService(session, sentinel_service=mock_sentinel)  # type: ignore[arg-type]
        report = await service.analyze(AnalyzeRequest(tenant_id="t", agent_id="a"))
        assert report.alert_created is True
        mock_sentinel.create_alert.assert_awaited_once()

    async def test_report_contains_baseline_id(self) -> None:
        baseline = _make_baseline()
        session = self._make_analyze_session(baseline, [])
        service = DriftDetectionService(session)  # type: ignore[arg-type]
        report = await service.analyze(AnalyzeRequest(tenant_id="t", agent_id="a"))
        assert report.baseline_id == baseline.id

    async def test_drift_score_tenant_and_agent_match_request(self) -> None:
        session = self._make_analyze_session(None, [])
        service = DriftDetectionService(session)  # type: ignore[arg-type]
        request = AnalyzeRequest(tenant_id="tenant-xyz", agent_id="agent-99")
        report = await service.analyze(request)
        assert report.drift_score.tenant_id == "tenant-xyz"
        assert report.drift_score.agent_id == "agent-99"

    async def test_recent_event_count_in_score(self) -> None:
        baseline = _make_baseline()
        recent = [_make_event_record() for _ in range(7)]
        session = self._make_analyze_session(baseline, recent)
        service = DriftDetectionService(session)  # type: ignore[arg-type]
        report = await service.analyze(AnalyzeRequest(tenant_id="t", agent_id="a"))
        assert report.drift_score.recent_event_count == 7
