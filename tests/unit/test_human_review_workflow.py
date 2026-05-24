"""Module 18 — LangGraph Workflows: human review graph tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from langgraph_workflows.human_review import HumanReviewState, build_human_review_graph

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _alert_id() -> str:
    return str(uuid4())


def _mock_alert(*, severity: str = "high", sentinel_type: str = "trajectory") -> MagicMock:
    alert = MagicMock()
    alert.severity = severity
    alert.sentinel_type = sentinel_type
    alert.message = "Agent behaved unexpectedly"
    return alert


def _sentinel_service(
    alert: MagicMock | None = None, *, raise_exc: Exception | None = None
) -> AsyncMock:
    svc = AsyncMock()
    if raise_exc:
        svc.get_alert = AsyncMock(side_effect=raise_exc)
    else:
        svc.get_alert = AsyncMock(return_value=alert or _mock_alert())
    svc.resolve_alert = AsyncMock()
    return svc


def _audit_service() -> AsyncMock:
    svc = AsyncMock()
    entry = MagicMock()
    entry.id = uuid4()
    svc.record = AsyncMock(return_value=entry)
    return svc


def _initial_state(aid: str | None = None, **overrides: object) -> HumanReviewState:
    base: HumanReviewState = {
        "alert_id": aid or _alert_id(),
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
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


class TestGraphCompiles:
    def test_compiles(self) -> None:
        graph = build_human_review_graph(_sentinel_service(), _audit_service())
        assert graph is not None


# ---------------------------------------------------------------------------
# load_alert node
# ---------------------------------------------------------------------------


class TestLoadAlert:
    async def test_populates_severity_from_alert(self) -> None:
        alert = _mock_alert(severity="critical")
        graph = build_human_review_graph(_sentinel_service(alert), _audit_service())
        result = await graph.ainvoke(_initial_state())
        assert result["alert_severity"] == "critical"

    async def test_populates_type_from_alert(self) -> None:
        alert = _mock_alert(sentinel_type="drift")
        graph = build_human_review_graph(_sentinel_service(alert), _audit_service())
        result = await graph.ainvoke(_initial_state())
        assert result["alert_type"] == "drift"

    async def test_error_on_missing_alert(self) -> None:
        svc = _sentinel_service(raise_exc=RuntimeError("not found"))
        graph = build_human_review_graph(svc, _audit_service())
        result = await graph.ainvoke(_initial_state())
        assert result["error"] == "not found"

    async def test_audit_not_called_when_alert_missing(self) -> None:
        svc = _sentinel_service(raise_exc=RuntimeError("gone"))
        audit = _audit_service()
        graph = build_human_review_graph(svc, audit)
        await graph.ainvoke(_initial_state())
        audit.record.assert_not_called()


# ---------------------------------------------------------------------------
# request_review node
# ---------------------------------------------------------------------------


class TestRequestReview:
    async def test_audit_called_on_review_request(self) -> None:
        audit = _audit_service()
        graph = build_human_review_graph(_sentinel_service(), audit)
        await graph.ainvoke(_initial_state())
        audit.record.assert_called_once()

    async def test_audit_action_is_human_review_requested(self) -> None:
        audit = _audit_service()
        graph = build_human_review_graph(_sentinel_service(), audit)
        await graph.ainvoke(_initial_state())
        call_kwargs = audit.record.call_args[0][0]
        assert call_kwargs.action == "human_review_requested"

    async def test_audit_entry_id_set(self) -> None:
        audit = _audit_service()
        graph = build_human_review_graph(_sentinel_service(), audit)
        result = await graph.ainvoke(_initial_state())
        assert result["audit_entry_id"] is not None

    async def test_no_decision_stops_after_request(self) -> None:
        svc = _sentinel_service()
        graph = build_human_review_graph(svc, _audit_service())
        result = await graph.ainvoke(_initial_state(decision=None))
        assert result["resolved"] is False
        svc.resolve_alert.assert_not_called()


# ---------------------------------------------------------------------------
# record_decision node
# ---------------------------------------------------------------------------


class TestRecordDecision:
    async def test_approve_decision_resolves_alert(self) -> None:
        svc = _sentinel_service()
        graph = build_human_review_graph(svc, _audit_service())
        result = await graph.ainvoke(_initial_state(decision="approve"))
        assert result["resolved"] is True
        svc.resolve_alert.assert_called_once()

    async def test_reject_decision_resolves_alert(self) -> None:
        svc = _sentinel_service()
        graph = build_human_review_graph(svc, _audit_service())
        result = await graph.ainvoke(_initial_state(decision="reject"))
        assert result["resolved"] is True

    async def test_escalate_decision_resolves_alert(self) -> None:
        svc = _sentinel_service()
        graph = build_human_review_graph(svc, _audit_service())
        result = await graph.ainvoke(_initial_state(decision="escalate"))
        assert result["resolved"] is True

    async def test_decision_audit_recorded(self) -> None:
        audit = _audit_service()
        graph = build_human_review_graph(_sentinel_service(), audit)
        await graph.ainvoke(_initial_state(decision="approve"))
        # First call: request_review; second: record_decision
        assert audit.record.call_count == 2

    async def test_decision_audit_action_name(self) -> None:
        audit = _audit_service()
        graph = build_human_review_graph(_sentinel_service(), audit)
        await graph.ainvoke(_initial_state(decision="approve"))
        last_call = audit.record.call_args_list[-1][0][0]
        assert last_call.action == "human_review_completed"

    async def test_reviewer_id_in_actor_email(self) -> None:
        audit = _audit_service()
        graph = build_human_review_graph(_sentinel_service(), audit)
        await graph.ainvoke(_initial_state(decision="approve", reviewer_id="alice@corp.com"))
        last_call = audit.record.call_args_list[-1][0][0]
        assert last_call.actor_email == "alice@corp.com"

    async def test_resolve_error_sets_error_field(self) -> None:
        svc = _sentinel_service()
        svc.resolve_alert = AsyncMock(side_effect=RuntimeError("db error"))
        graph = build_human_review_graph(svc, _audit_service())
        result = await graph.ainvoke(_initial_state(decision="approve"))
        assert result["resolved"] is False
        assert result["error"] is not None
