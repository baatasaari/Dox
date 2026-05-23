"""Module 18 — LangGraph Workflows: session replay graph tests."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from langgraph_workflows.replay import ReplayState, build_replay_graph

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event_record(event_type: str, agent_id: str = "ag", ts: datetime | None = None) -> MagicMock:
    record = MagicMock()
    record.event_id = uuid4()
    record.event_type = event_type
    record.agent_id = agent_id
    record.timestamp = ts or datetime.now(UTC)
    record.payload = {}
    return record


def _query_service(
    records: list[MagicMock] | None = None, *, raise_exc: Exception | None = None
) -> AsyncMock:
    svc = AsyncMock()
    if raise_exc:
        svc.list_events = AsyncMock(side_effect=raise_exc)
    else:
        svc.list_events = AsyncMock(return_value=records or [])
    return svc


def _audit_service() -> AsyncMock:
    svc = AsyncMock()
    entry = MagicMock()
    entry.id = uuid4()
    svc.record = AsyncMock(return_value=entry)
    return svc


def _initial_state(**overrides: object) -> ReplayState:
    base: ReplayState = {
        "tenant_id": "acme",
        "session_id": "sess-001",
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
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


class TestGraphCompiles:
    def test_compiles_without_audit_service(self) -> None:
        graph = build_replay_graph(_query_service())
        assert graph is not None

    def test_compiles_with_audit_service(self) -> None:
        graph = build_replay_graph(_query_service(), _audit_service())
        assert graph is not None


# ---------------------------------------------------------------------------
# load_events node
# ---------------------------------------------------------------------------


class TestLoadEvents:
    async def test_events_loaded_from_query_service(self) -> None:
        records = [_event_record("agent_started"), _event_record("agent_completed")]
        graph = build_replay_graph(_query_service(records))
        result = await graph.ainvoke(_initial_state())
        assert len(result["events"]) == 2

    async def test_events_sorted_by_timestamp(self) -> None:
        t1 = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
        t2 = datetime(2024, 1, 1, 11, 0, tzinfo=UTC)
        records = [_event_record("agent_completed", ts=t2), _event_record("agent_started", ts=t1)]
        graph = build_replay_graph(_query_service(records))
        result = await graph.ainvoke(_initial_state())
        types = [e["event_type"] for e in result["events"]]
        assert types == ["agent_started", "agent_completed"]

    async def test_load_error_sets_error_field(self) -> None:
        graph = build_replay_graph(_query_service(raise_exc=RuntimeError("db error")))
        result = await graph.ainvoke(_initial_state())
        assert result["error"] == "db error"

    async def test_load_error_stops_graph(self) -> None:
        graph = build_replay_graph(_query_service(raise_exc=RuntimeError("fail")))
        result = await graph.ainvoke(_initial_state())
        assert result["completed"] is False

    async def test_empty_events_stops_graph(self) -> None:
        graph = build_replay_graph(_query_service([]))
        result = await graph.ainvoke(_initial_state())
        assert result["completed"] is False


# ---------------------------------------------------------------------------
# validate_events node
# ---------------------------------------------------------------------------


class TestValidateEvents:
    async def test_has_agent_started_true(self) -> None:
        records = [_event_record("agent_started"), _event_record("agent_completed")]
        graph = build_replay_graph(_query_service(records))
        result = await graph.ainvoke(_initial_state())
        assert result["has_agent_started"] is True

    async def test_has_agent_completed_true(self) -> None:
        records = [_event_record("agent_started"), _event_record("agent_completed")]
        graph = build_replay_graph(_query_service(records))
        result = await graph.ainvoke(_initial_state())
        assert result["has_agent_completed"] is True

    async def test_agent_failed_counts_as_completed(self) -> None:
        records = [_event_record("agent_started"), _event_record("agent_failed")]
        graph = build_replay_graph(_query_service(records))
        result = await graph.ainvoke(_initial_state())
        assert result["has_agent_completed"] is True

    async def test_incomplete_session_flags_false(self) -> None:
        records = [_event_record("tool_call_started"), _event_record("tool_call_completed")]
        graph = build_replay_graph(_query_service(records))
        result = await graph.ainvoke(_initial_state())
        assert result["has_agent_started"] is False
        assert result["has_agent_completed"] is False


# ---------------------------------------------------------------------------
# replay_events node
# ---------------------------------------------------------------------------


class TestReplayEvents:
    async def test_replayed_count_matches_event_count(self) -> None:
        event_types = ["agent_started", "tool_call_started", "agent_completed"]
        records = [_event_record(t) for t in event_types]
        graph = build_replay_graph(_query_service(records))
        result = await graph.ainvoke(_initial_state())
        assert result["replayed_count"] == 3

    async def test_skipped_count_zero_on_clean_events(self) -> None:
        records = [_event_record("agent_started")]
        graph = build_replay_graph(_query_service(records))
        result = await graph.ainvoke(_initial_state())
        assert result["skipped_count"] == 0

    async def test_replay_log_has_one_entry_per_event(self) -> None:
        records = [_event_record("agent_started"), _event_record("agent_completed")]
        graph = build_replay_graph(_query_service(records))
        result = await graph.ainvoke(_initial_state())
        assert len(result["replay_log"]) == 2

    async def test_replay_log_contains_event_types(self) -> None:
        records = [_event_record("agent_started")]
        graph = build_replay_graph(_query_service(records))
        result = await graph.ainvoke(_initial_state())
        assert "agent_started" in result["replay_log"][0]


# ---------------------------------------------------------------------------
# summarize node
# ---------------------------------------------------------------------------


class TestSummarize:
    async def test_completed_true_after_summarize(self) -> None:
        records = [_event_record("agent_started")]
        graph = build_replay_graph(_query_service(records))
        result = await graph.ainvoke(_initial_state())
        assert result["completed"] is True

    async def test_audit_called_when_audit_service_provided(self) -> None:
        records = [_event_record("agent_started", agent_id="my-agent")]
        audit = _audit_service()
        graph = build_replay_graph(_query_service(records), audit)
        await graph.ainvoke(_initial_state())
        audit.record.assert_called_once()

    async def test_audit_not_called_without_audit_service(self) -> None:
        records = [_event_record("agent_started")]
        graph = build_replay_graph(_query_service(records))
        result = await graph.ainvoke(_initial_state())
        assert result["completed"] is True

    async def test_audit_action_is_replay_completed(self) -> None:
        records = [_event_record("agent_started")]
        audit = _audit_service()
        graph = build_replay_graph(_query_service(records), audit)
        await graph.ainvoke(_initial_state())
        call = audit.record.call_args[0][0]
        assert call.action == "replay_completed"

    async def test_audit_resource_id_is_session_id(self) -> None:
        records = [_event_record("agent_started")]
        audit = _audit_service()
        graph = build_replay_graph(_query_service(records), audit)
        await graph.ainvoke(_initial_state(session_id="my-session"))
        call = audit.record.call_args[0][0]
        assert call.resource_id == "my-session"
