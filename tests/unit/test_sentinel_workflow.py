"""Module 18 — LangGraph Workflows: sentinel response graph tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from langgraph_workflows.sentinels import SentinelResponseState, build_sentinel_response_graph

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _alert_id() -> str:
    return str(uuid4())


def _mock_alert(
    *, severity: str = "high", sentinel_type: str = "trajectory", agent_id: str = "ag"
) -> MagicMock:
    alert = MagicMock()
    alert.severity = severity
    alert.sentinel_type = sentinel_type
    alert.message = "Policy breach detected"
    alert.agent_id = agent_id
    return alert


def _mock_policy(*, sentinel_type: str = "trajectory", action: str = "pause_agent") -> MagicMock:
    policy = MagicMock()
    policy.id = uuid4()
    policy.sentinel_type = sentinel_type
    policy.action = action
    return policy


def _sentinel_service(
    alert: MagicMock | None = None,
    policies: list[MagicMock] | None = None,
    *,
    raise_on_get: Exception | None = None,
) -> AsyncMock:
    svc = AsyncMock()
    if raise_on_get:
        svc.get_alert = AsyncMock(side_effect=raise_on_get)
    else:
        svc.get_alert = AsyncMock(return_value=alert or _mock_alert())
    svc.list_policies = AsyncMock(return_value=policies or [])
    svc.resolve_alert = AsyncMock()
    return svc


def _audit_service() -> AsyncMock:
    svc = AsyncMock()
    entry = MagicMock()
    entry.id = uuid4()
    svc.record = AsyncMock(return_value=entry)
    return svc


def _initial_state(aid: str | None = None, **overrides: object) -> SentinelResponseState:
    base: SentinelResponseState = {
        "alert_id": aid or _alert_id(),
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
    base.update(overrides)  # type: ignore[typeddict-item]
    base["alert_id"] = aid or base["alert_id"]
    return base


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


class TestGraphCompiles:
    def test_compiles(self) -> None:
        graph = build_sentinel_response_graph(_sentinel_service(), _audit_service())
        assert graph is not None


# ---------------------------------------------------------------------------
# load_alert node
# ---------------------------------------------------------------------------


class TestLoadAlert:
    async def test_populates_severity(self) -> None:
        alert = _mock_alert(severity="critical")
        graph = build_sentinel_response_graph(_sentinel_service(alert), _audit_service())
        result = await graph.ainvoke(_initial_state())
        assert result["alert_severity"] == "critical"

    async def test_populates_agent_id(self) -> None:
        alert = _mock_alert(agent_id="my-bot")
        graph = build_sentinel_response_graph(_sentinel_service(alert), _audit_service())
        result = await graph.ainvoke(_initial_state())
        assert result["agent_id"] == "my-bot"

    async def test_error_on_get_alert_failure(self) -> None:
        svc = _sentinel_service(raise_on_get=RuntimeError("not found"))
        graph = build_sentinel_response_graph(svc, _audit_service())
        result = await graph.ainvoke(_initial_state())
        assert result["error"] == "not found"

    async def test_error_stops_graph_before_audit(self) -> None:
        audit = _audit_service()
        svc = _sentinel_service(raise_on_get=RuntimeError("gone"))
        graph = build_sentinel_response_graph(svc, audit)
        result = await graph.ainvoke(_initial_state())
        assert result["resolved"] is False
        audit.record.assert_not_called()


# ---------------------------------------------------------------------------
# find_policy node
# ---------------------------------------------------------------------------


class TestFindPolicy:
    async def test_policy_matched_by_sentinel_type(self) -> None:
        alert = _mock_alert(sentinel_type="drift")
        policy = _mock_policy(sentinel_type="drift", action="pause_agent")
        svc = _sentinel_service(alert, [policy])
        graph = build_sentinel_response_graph(svc, _audit_service())
        result = await graph.ainvoke(_initial_state())
        assert result["matched_policy_id"] == str(policy.id)

    async def test_action_taken_from_policy(self) -> None:
        alert = _mock_alert(sentinel_type="drift")
        policy = _mock_policy(sentinel_type="drift", action="pause_agent")
        svc = _sentinel_service(alert, [policy])
        graph = build_sentinel_response_graph(svc, _audit_service())
        result = await graph.ainvoke(_initial_state())
        assert result["action_taken"] == "pause_agent"

    async def test_no_matching_policy_sets_none(self) -> None:
        alert = _mock_alert(sentinel_type="drift")
        policy = _mock_policy(sentinel_type="tool_misuse")
        svc = _sentinel_service(alert, [policy])
        graph = build_sentinel_response_graph(svc, _audit_service())
        result = await graph.ainvoke(_initial_state())
        assert result["matched_policy_id"] is None

    async def test_no_policies_leads_to_default_resolution(self) -> None:
        svc = _sentinel_service(policies=[])
        graph = build_sentinel_response_graph(svc, _audit_service())
        result = await graph.ainvoke(_initial_state())
        assert result["resolved"] is True
        assert result["action_taken"] == "warn"


# ---------------------------------------------------------------------------
# execute_action / resolve_with_default
# ---------------------------------------------------------------------------


class TestExecuteAction:
    async def test_resolve_alert_called_with_policy_action(self) -> None:
        alert = _mock_alert(sentinel_type="drift")
        policy = _mock_policy(sentinel_type="drift", action="pause_agent")
        svc = _sentinel_service(alert, [policy])
        graph = build_sentinel_response_graph(svc, _audit_service())
        await graph.ainvoke(_initial_state())
        svc.resolve_alert.assert_called_once()

    async def test_resolved_true_after_execute(self) -> None:
        alert = _mock_alert(sentinel_type="drift")
        policy = _mock_policy(sentinel_type="drift", action="warn")
        svc = _sentinel_service(alert, [policy])
        graph = build_sentinel_response_graph(svc, _audit_service())
        result = await graph.ainvoke(_initial_state())
        assert result["resolved"] is True

    async def test_default_warn_when_no_policy(self) -> None:
        svc = _sentinel_service(policies=[])
        graph = build_sentinel_response_graph(svc, _audit_service())
        result = await graph.ainvoke(_initial_state())
        assert result["action_taken"] == "warn"
        assert result["resolved"] is True


# ---------------------------------------------------------------------------
# record_outcome node
# ---------------------------------------------------------------------------


class TestRecordOutcome:
    async def test_audit_called_after_resolution(self) -> None:
        audit = _audit_service()
        graph = build_sentinel_response_graph(_sentinel_service(), audit)
        await graph.ainvoke(_initial_state())
        audit.record.assert_called_once()

    async def test_audit_entry_id_set_in_state(self) -> None:
        audit = _audit_service()
        graph = build_sentinel_response_graph(_sentinel_service(), audit)
        result = await graph.ainvoke(_initial_state())
        assert result["audit_entry_id"] is not None

    async def test_audit_action_is_sentinel_response_applied(self) -> None:
        audit = _audit_service()
        graph = build_sentinel_response_graph(_sentinel_service(), audit)
        await graph.ainvoke(_initial_state())
        call = audit.record.call_args[0][0]
        assert call.action == "sentinel_response_applied"

    async def test_audit_resource_id_is_alert_id(self) -> None:
        aid = _alert_id()
        audit = _audit_service()
        graph = build_sentinel_response_graph(_sentinel_service(), audit)
        await graph.ainvoke(_initial_state(aid=aid))
        call = audit.record.call_args[0][0]
        assert call.resource_id == aid

    async def test_audit_extra_contains_resolved_flag(self) -> None:
        audit = _audit_service()
        graph = build_sentinel_response_graph(_sentinel_service(), audit)
        await graph.ainvoke(_initial_state())
        call = audit.record.call_args[0][0]
        assert "resolved" in call.extra
