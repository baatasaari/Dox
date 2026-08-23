"""Unit tests for PlaybackService — state reconstruction and frame indexing.

These tests exercise the pure logic of PlaybackService without a real database.
The AsyncSession is replaced with a lightweight mock that returns pre-built
EventRecord instances, so every test is synchronous-fast and needs no fixtures.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common.models.event import EventRecord
from common.models.replay import SessionReplay
from common.schemas.validators import compute_payload_hash
from services.playback.service import PlaybackService, _payload_summary

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts(offset_seconds: float = 0.0) -> datetime:
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    return base + timedelta(seconds=offset_seconds)


def _event(
    event_type: str,
    payload: dict | None = None,
    offset_seconds: float = 0.0,
    session_id: str = "sess-1",
    tenant_id: str = "tenant-1",
) -> EventRecord:
    p = payload or {}
    r = MagicMock(spec=EventRecord)
    r.event_id = uuid4()
    r.event_type = event_type
    r.session_id = session_id
    r.tenant_id = tenant_id
    r.agent_id = "agent-1"
    r.timestamp = _ts(offset_seconds)
    r.created_at = _ts(offset_seconds)
    r.payload = p
    r.payload_hash = compute_payload_hash(p)
    return r


def _make_service(events: list[EventRecord]) -> PlaybackService:
    """Return a PlaybackService whose _load_ordered_events returns *events*."""
    session = AsyncMock()
    svc = PlaybackService(session)
    svc._load_ordered_events = AsyncMock(return_value=events)
    return svc


def _make_replay(events: list[EventRecord]) -> SessionReplay:
    """Build a SessionReplay from a list of events (same logic as service.create)."""
    started = events[0].timestamp if events else None
    replay_log = [
        {
            "seq": i,
            "event_id": str(e.event_id),
            "event_type": e.event_type,
            "timestamp": e.timestamp.isoformat(),
            "elapsed_seconds": (
                (e.timestamp - started).total_seconds() if started else 0.0
            ),
        }
        for i, e in enumerate(events)
    ]
    r = MagicMock(spec=SessionReplay)
    r.id = uuid4()
    r.tenant_id = "tenant-1"
    r.original_session_id = "sess-1"
    r.agent_id = "agent-1"
    r.name = "Test replay"
    r.status = "pending"
    r.total_events = len(events)
    r.current_position = 0
    r.speed_factor = 0.0
    r.replay_log = replay_log
    r.context_window = {}
    return r


# ---------------------------------------------------------------------------
# _payload_summary
# ---------------------------------------------------------------------------


class TestPayloadSummary:
    def test_extracts_known_keys(self) -> None:
        payload = {
            "tool_name": "web_search",
            "query": "python asyncio",
            "irrelevant_key": "should be dropped",
            "tokens": 128,
        }
        summary = _payload_summary(payload)
        assert summary == {"tool_name": "web_search", "query": "python asyncio", "tokens": 128}

    def test_empty_payload_returns_empty(self) -> None:
        assert _payload_summary({}) == {}

    def test_no_matching_keys_returns_empty(self) -> None:
        assert _payload_summary({"unknown": "value", "also_unknown": 42}) == {}


# ---------------------------------------------------------------------------
# get_frames
# ---------------------------------------------------------------------------


class TestGetFrames:
    async def test_returns_ordered_frames(self) -> None:
        events = [_event("agent_started", offset_seconds=i) for i in range(3)]
        svc = _make_service(events)
        replay = _make_replay(events)
        svc.get = AsyncMock(return_value=replay)

        frames = await svc.get_frames(replay.id)

        assert len(frames) == 3
        assert [f.sequence_num for f in frames] == [0, 1, 2]
        assert all(f.event_type == "agent_started" for f in frames)

    async def test_elapsed_seconds_increase_monotonically(self) -> None:
        events = [_event("tool_call_started", offset_seconds=i * 5) for i in range(4)]
        svc = _make_service(events)
        replay = _make_replay(events)
        svc.get = AsyncMock(return_value=replay)

        frames = await svc.get_frames(replay.id)
        elapsed = [f.elapsed_seconds for f in frames]

        assert elapsed == sorted(elapsed)
        assert elapsed[0] == 0.0
        assert elapsed[-1] == pytest.approx(15.0)

    async def test_empty_session_returns_empty_frames(self) -> None:
        svc = _make_service([])
        replay = _make_replay([])
        svc.get = AsyncMock(return_value=replay)

        frames = await svc.get_frames(replay.id)
        assert frames == []


# ---------------------------------------------------------------------------
# get_state_at — memory accumulation
# ---------------------------------------------------------------------------


class TestGetStateAtMemory:
    """Memory writes and rollbacks are tracked correctly."""

    async def test_approved_write_appears_in_memory(self) -> None:
        mem_id = str(uuid4())
        events = [
            _event("agent_started", offset_seconds=0),
            _event(
                "memory_write_approved",
                payload={"content": "capital of France is Paris"},
                offset_seconds=1,
            ),
        ]
        # Give the second event a known event_id for assertion.
        events[1].event_id = mem_id  # type: ignore[assignment]

        svc = _make_service(events)
        replay = _make_replay(events)
        svc.get = AsyncMock(return_value=replay)

        state = await svc.get_state_at(replay.id, position=2)

        assert len(state.memory) == 1
        assert state.memory[0]["event_id"] == str(mem_id)

    async def test_rolled_back_write_excluded_from_memory(self) -> None:
        mem_event_id = str(uuid4())

        events = [
            _event("agent_started", offset_seconds=0),
            _event(
                "memory_write_approved",
                payload={"content": "wrong fact"},
                offset_seconds=1,
            ),
            _event(
                "memory_rollback",
                payload={"target_event_id": mem_event_id},
                offset_seconds=2,
            ),
        ]
        events[1].event_id = mem_event_id  # type: ignore[assignment]

        svc = _make_service(events)
        replay = _make_replay(events)
        svc.get = AsyncMock(return_value=replay)

        state = await svc.get_state_at(replay.id, position=3)

        assert state.memory == [], "Rolled-back write must not appear in active memory"

    async def test_non_rolled_back_writes_survive(self) -> None:
        mem_a = str(uuid4())
        mem_b = str(uuid4())

        events = [
            _event("memory_write_approved", payload={"content": "A"}, offset_seconds=0),
            _event("memory_write_approved", payload={"content": "B"}, offset_seconds=1),
            _event(
                "memory_rollback",
                payload={"target_event_id": mem_a},
                offset_seconds=2,
            ),
        ]
        events[0].event_id = mem_a  # type: ignore[assignment]
        events[1].event_id = mem_b  # type: ignore[assignment]

        svc = _make_service(events)
        replay = _make_replay(events)
        svc.get = AsyncMock(return_value=replay)

        state = await svc.get_state_at(replay.id, position=3)

        assert len(state.memory) == 1
        assert state.memory[0]["event_id"] == str(mem_b)


# ---------------------------------------------------------------------------
# get_state_at — tool call tracking
# ---------------------------------------------------------------------------


class TestGetStateAtToolCalls:
    """Open tool calls (started but not completed) are tracked."""

    async def test_open_tool_call_appears_in_active(self) -> None:
        tool_id = str(uuid4())
        events = [
            _event("tool_call_started", payload={"tool_name": "search"}, offset_seconds=0),
        ]
        events[0].event_id = tool_id  # type: ignore[assignment]

        svc = _make_service(events)
        replay = _make_replay(events)
        svc.get = AsyncMock(return_value=replay)

        state = await svc.get_state_at(replay.id, position=1)
        assert tool_id in state.active_tool_calls

    async def test_completed_tool_call_removed_from_active(self) -> None:
        tool_id = str(uuid4())
        events = [
            _event("tool_call_started", payload={"tool_name": "search"}, offset_seconds=0),
            _event(
                "tool_call_completed",
                payload={"parent_event_id": tool_id, "result": "ok"},
                offset_seconds=1,
            ),
        ]
        events[0].event_id = tool_id  # type: ignore[assignment]

        svc = _make_service(events)
        replay = _make_replay(events)
        svc.get = AsyncMock(return_value=replay)

        state = await svc.get_state_at(replay.id, position=2)
        assert state.active_tool_calls == []

    async def test_failed_tool_call_removed_from_active(self) -> None:
        tool_id = str(uuid4())
        events = [
            _event("tool_call_started", payload={}, offset_seconds=0),
            _event(
                "tool_call_failed",
                payload={"parent_event_id": tool_id, "reason": "timeout"},
                offset_seconds=1,
            ),
        ]
        events[0].event_id = tool_id  # type: ignore[assignment]

        svc = _make_service(events)
        replay = _make_replay(events)
        svc.get = AsyncMock(return_value=replay)

        state = await svc.get_state_at(replay.id, position=2)
        assert state.active_tool_calls == []


# ---------------------------------------------------------------------------
# get_state_at — alerts and interventions
# ---------------------------------------------------------------------------


class TestGetStateAtAlerts:
    async def test_sentinel_alert_accumulated(self) -> None:
        events = [
            _event(
                "sentinel_alert_created",
                payload={"message": "policy breach detected"},
                offset_seconds=0,
            ),
        ]
        svc = _make_service(events)
        replay = _make_replay(events)
        svc.get = AsyncMock(return_value=replay)

        state = await svc.get_state_at(replay.id, position=1)
        assert "policy breach detected" in state.sentinel_alerts

    async def test_intervention_accumulated(self) -> None:
        events = [
            _event(
                "intervention_applied",
                payload={"action": "block_tool_call"},
                offset_seconds=0,
            ),
        ]
        svc = _make_service(events)
        replay = _make_replay(events)
        svc.get = AsyncMock(return_value=replay)

        state = await svc.get_state_at(replay.id, position=1)
        assert "block_tool_call" in state.interventions


# ---------------------------------------------------------------------------
# get_state_at — position clamping and event_type_counts
# ---------------------------------------------------------------------------


class TestGetStateAtMisc:
    async def test_position_clamped_to_total_events(self) -> None:
        events = [_event("agent_started", offset_seconds=i) for i in range(3)]
        svc = _make_service(events)
        replay = _make_replay(events)
        svc.get = AsyncMock(return_value=replay)

        state = await svc.get_state_at(replay.id, position=999)
        assert state.position == 3

    async def test_position_zero_returns_empty_state(self) -> None:
        events = [_event("agent_started", offset_seconds=0)]
        svc = _make_service(events)
        replay = _make_replay(events)
        svc.get = AsyncMock(return_value=replay)

        state = await svc.get_state_at(replay.id, position=0)
        assert state.position == 0
        assert state.context_window == []
        assert state.memory == []
        assert state.active_tool_calls == []

    async def test_event_type_counts_histogram(self) -> None:
        events = [
            _event("tool_call_started", offset_seconds=0),
            _event("tool_call_started", offset_seconds=1),
            _event("tool_call_completed", payload={"parent_event_id": "x"}, offset_seconds=2),
            _event("model_called", offset_seconds=3),
        ]
        svc = _make_service(events)
        replay = _make_replay(events)
        svc.get = AsyncMock(return_value=replay)

        state = await svc.get_state_at(replay.id, position=4)
        assert state.event_type_counts["tool_call_started"] == 2
        assert state.event_type_counts["tool_call_completed"] == 1
        assert state.event_type_counts["model_called"] == 1

    async def test_context_window_capped_at_twenty(self) -> None:
        events = [_event("model_called", offset_seconds=float(i)) for i in range(30)]
        svc = _make_service(events)
        replay = _make_replay(events)
        svc.get = AsyncMock(return_value=replay)

        state = await svc.get_state_at(replay.id, position=30)
        assert len(state.context_window) == 20

    async def test_current_agent_step_tracks_open_steps(self) -> None:
        events = [
            _event("agent_step_started", offset_seconds=0),
            _event("agent_step_started", offset_seconds=1),
            _event("agent_step_completed", offset_seconds=2),
        ]
        svc = _make_service(events)
        replay = _make_replay(events)
        svc.get = AsyncMock(return_value=replay)

        state = await svc.get_state_at(replay.id, position=3)
        # 2 started, 1 completed → 1 still open
        assert state.current_agent_step == 1
