"""Module 18 — LangGraph Workflows: end-to-end integration tests."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from langgraph_workflows.drift_analysis import build_drift_analysis_graph
from langgraph_workflows.human_review import build_human_review_graph
from langgraph_workflows.replay import build_replay_graph
from langgraph_workflows.sentinels import build_sentinel_response_graph

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _drift_report(score: float, severity: str, deviations: int = 0) -> MagicMock:
    report = MagicMock()
    report.drift_score.score = score
    report.drift_score.severity = severity
    report.drift_score.deviations = [MagicMock() for _ in range(deviations)]
    report.alert_created = severity in ("high", "critical")
    return report


def _event_record(event_type: str, ts: datetime | None = None) -> MagicMock:
    record = MagicMock()
    record.event_id = uuid4()
    record.event_type = event_type
    record.agent_id = "integration-agent"
    record.timestamp = ts or datetime.now(UTC)
    record.payload = {}
    return record


def _mock_alert(severity: str = "high", sentinel_type: str = "drift") -> MagicMock:
    alert = MagicMock()
    alert.severity = severity
    alert.sentinel_type = sentinel_type
    alert.message = "Drift detected in production"
    alert.agent_id = "integration-agent"
    return alert


def _mock_policy(sentinel_type: str = "drift", action: str = "pause_agent") -> MagicMock:
    policy = MagicMock()
    policy.id = uuid4()
    policy.sentinel_type = sentinel_type
    policy.action = action
    return policy


def _audit_stub() -> AsyncMock:
    svc = AsyncMock()
    entry = MagicMock()
    entry.id = uuid4()
    svc.record = AsyncMock(return_value=entry)
    return svc


# ---------------------------------------------------------------------------
# Drift analysis integration
# ---------------------------------------------------------------------------


class TestDriftAnalysisIntegration:
    async def test_high_drift_triggers_audit_entry(self) -> None:
        drift_svc = AsyncMock()
        drift_svc.analyze = AsyncMock(return_value=_drift_report(0.85, "high", deviations=4))
        audit = _audit_stub()
        graph = build_drift_analysis_graph(drift_svc, audit)
        result = await graph.ainvoke(
            {
                "tenant_id": "acme",
                "agent_id": "prod-agent",
                "lookback_hours": 2,
                "drift_score": None,
                "severity": None,
                "deviations_count": 0,
                "alert_created": False,
                "audit_entry_id": None,
                "error": None,
            }
        )
        assert result["severity"] == "high"
        assert result["drift_score"] == 0.85
        audit.record.assert_called_once()
        call = audit.record.call_args[0][0]
        assert call.resource_id == "prod-agent"
        assert call.extra["deviations_count"] == 4

    async def test_no_drift_skips_audit(self) -> None:
        drift_svc = AsyncMock()
        drift_svc.analyze = AsyncMock(return_value=_drift_report(0.02, "none"))
        audit = _audit_stub()
        graph = build_drift_analysis_graph(drift_svc, audit)
        result = await graph.ainvoke(
            {
                "tenant_id": "acme",
                "agent_id": "calm-agent",
                "lookback_hours": 1,
                "drift_score": None,
                "severity": None,
                "deviations_count": 0,
                "alert_created": False,
                "audit_entry_id": None,
                "error": None,
            }
        )
        assert result["severity"] == "none"
        audit.record.assert_not_called()


# ---------------------------------------------------------------------------
# Human review integration
# ---------------------------------------------------------------------------


class TestHumanReviewIntegration:
    async def test_full_approve_flow(self) -> None:
        alert_id = str(uuid4())
        sentinel_svc = AsyncMock()
        sentinel_svc.get_alert = AsyncMock(return_value=_mock_alert())
        sentinel_svc.resolve_alert = AsyncMock()
        audit = _audit_stub()

        graph = build_human_review_graph(sentinel_svc, audit)
        result = await graph.ainvoke(
            {
                "alert_id": alert_id,
                "tenant_id": "acme",
                "alert_severity": None,
                "alert_type": None,
                "alert_message": None,
                "reviewer_id": "reviewer@acme.com",
                "decision": "approve",
                "notes": "Looks acceptable",
                "audit_entry_id": None,
                "resolved": False,
                "error": None,
            }
        )
        assert result["resolved"] is True
        assert result["error"] is None
        # Two audit entries: request + decision
        assert audit.record.call_count == 2
        sentinel_svc.resolve_alert.assert_called_once()

    async def test_no_decision_leaves_resolved_false(self) -> None:
        sentinel_svc = AsyncMock()
        sentinel_svc.get_alert = AsyncMock(return_value=_mock_alert())
        sentinel_svc.resolve_alert = AsyncMock()
        audit = _audit_stub()

        graph = build_human_review_graph(sentinel_svc, audit)
        result = await graph.ainvoke(
            {
                "alert_id": str(uuid4()),
                "tenant_id": "acme",
                "alert_severity": None,
                "alert_type": None,
                "alert_message": None,
                "reviewer_id": None,
                "decision": None,
                "notes": None,
                "audit_entry_id": None,
                "resolved": False,
                "error": None,
            }
        )
        assert result["resolved"] is False
        sentinel_svc.resolve_alert.assert_not_called()
        # Only request_review audit entry
        assert audit.record.call_count == 1


# ---------------------------------------------------------------------------
# Replay integration
# ---------------------------------------------------------------------------


class TestReplayIntegration:
    async def test_complete_session_replay(self) -> None:
        from datetime import timedelta

        t0 = datetime(2024, 6, 1, 10, 0, tzinfo=UTC)
        records = [
            _event_record("agent_started", ts=t0),
            _event_record("tool_call_started", ts=t0 + timedelta(seconds=1)),
            _event_record("tool_call_completed", ts=t0 + timedelta(seconds=2)),
            _event_record("agent_completed", ts=t0 + timedelta(seconds=3)),
        ]
        query_svc = AsyncMock()
        query_svc.list_events = AsyncMock(return_value=records)
        audit = _audit_stub()

        graph = build_replay_graph(query_svc, audit)
        result = await graph.ainvoke(
            {
                "tenant_id": "acme",
                "session_id": "sess-xyz",
                "agent_id": "integration-agent",
                "events": [],
                "replayed_count": 0,
                "skipped_count": 0,
                "replay_log": [],
                "has_agent_started": False,
                "has_agent_completed": False,
                "error": None,
                "completed": False,
            }
        )
        assert result["completed"] is True
        assert result["replayed_count"] == 4
        assert result["has_agent_started"] is True
        assert result["has_agent_completed"] is True
        assert len(result["replay_log"]) == 4
        audit.record.assert_called_once()
        call = audit.record.call_args[0][0]
        assert call.resource_id == "sess-xyz"

    async def test_empty_session_does_not_complete(self) -> None:
        query_svc = AsyncMock()
        query_svc.list_events = AsyncMock(return_value=[])
        graph = build_replay_graph(query_svc)
        result = await graph.ainvoke(
            {
                "tenant_id": "acme",
                "session_id": "sess-empty",
                "agent_id": None,
                "events": [],
                "replayed_count": 0,
                "skipped_count": 0,
                "replay_log": [],
                "has_agent_started": False,
                "has_agent_completed": False,
                "error": None,
                "completed": False,
            }
        )
        assert result["completed"] is False


# ---------------------------------------------------------------------------
# Sentinel response integration
# ---------------------------------------------------------------------------


class TestSentinelResponseIntegration:
    async def test_policy_match_resolves_with_correct_action(self) -> None:
        alert = _mock_alert(severity="high", sentinel_type="drift")
        policy = _mock_policy(sentinel_type="drift", action="pause_agent")
        sentinel_svc = AsyncMock()
        sentinel_svc.get_alert = AsyncMock(return_value=alert)
        sentinel_svc.list_policies = AsyncMock(return_value=[policy])
        sentinel_svc.resolve_alert = AsyncMock()
        audit = _audit_stub()

        graph = build_sentinel_response_graph(sentinel_svc, audit)
        result = await graph.ainvoke(
            {
                "alert_id": str(uuid4()),
                "tenant_id": "acme",
                "alert_severity": None,
                "alert_type": None,
                "alert_message": None,
                "agent_id": None,
                "matched_policy_id": None,
                "action_taken": None,
                "audit_entry_id": None,
                "resolved": False,
                "error": None,
            }
        )
        assert result["resolved"] is True
        assert result["action_taken"] == "pause_agent"
        assert result["matched_policy_id"] == str(policy.id)
        audit.record.assert_called_once()
        call = audit.record.call_args[0][0]
        assert call.extra["action_taken"] == "pause_agent"

    async def test_no_policy_falls_back_to_warn(self) -> None:
        sentinel_svc = AsyncMock()
        sentinel_svc.get_alert = AsyncMock(return_value=_mock_alert())
        sentinel_svc.list_policies = AsyncMock(return_value=[])
        sentinel_svc.resolve_alert = AsyncMock()
        audit = _audit_stub()

        graph = build_sentinel_response_graph(sentinel_svc, audit)
        result = await graph.ainvoke(
            {
                "alert_id": str(uuid4()),
                "tenant_id": "acme",
                "alert_severity": None,
                "alert_type": None,
                "alert_message": None,
                "agent_id": None,
                "matched_policy_id": None,
                "action_taken": None,
                "audit_entry_id": None,
                "resolved": False,
                "error": None,
            }
        )
        assert result["resolved"] is True
        assert result["action_taken"] == "warn"
        assert result["audit_entry_id"] is not None
