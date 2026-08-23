"""Session Playback Service — record, step through, and reconstruct agentic sessions.

Architecture
------------
Every agentic session emits a stream of :class:`~common.models.event.EventRecord`
rows keyed by ``session_id``.  A :class:`SessionReplay` (persisted in
``session_replays``) is a *view* over that stream: it stores an ordered
``replay_log`` (pre-computed frame index) and the ``context_window`` (accumulated
state snapshot at ``current_position``).

The three principal operations are:

``create``
    Loads all ``EventRecord`` rows for ``original_session_id``, sorts them by
    ``timestamp``, builds the frame index, and persists a new ``SessionReplay``.

``get_state_at(replay_id, position)``
    Folds over the first *position* frames and returns an :class:`AccumulatedState`
    that captures what the agent knew at that exact moment: approved memory, open
    tool calls, sentinel alerts, interventions, and a sliding context window.

``step(replay_id)``
    Advances ``current_position`` by one and persists an updated
    ``context_window`` snapshot.

``run(replay_id)``
    Delegates to the pre-existing LangGraph ``build_replay_graph`` workflow which
    walks every frame, optionally writes an audit entry, and marks the replay
    ``completed``.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import NotFoundError
from common.models.event import EventRecord
from common.models.replay import SessionReplay
from common.schemas.replay import (
    AccumulatedState,
    ReplayFrame,
    SessionReplayCreate,
)

# Maximum events included in the sliding context window visible to the caller.
_CONTEXT_WINDOW_SIZE = 20

# Keys extracted from a frame's payload for the compact summary.
_SUMMARY_KEYS = {
    "tool_name", "tool_id", "result", "query", "content",
    "action", "message", "reason", "model", "tokens",
}


def _payload_summary(payload: dict) -> dict:
    """Return a subset of payload keys relevant to debugging/replay UI."""
    return {k: v for k, v in payload.items() if k in _SUMMARY_KEYS}


class PlaybackService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create(self, create: SessionReplayCreate) -> SessionReplay:
        """Build a replay index from existing events and persist it.

        Steps:
        1. Load all EventRecords for ``original_session_id`` ordered by timestamp.
        2. Infer ``agent_id`` from the first event if not provided.
        3. Build ``replay_log`` — one compact frame dict per event.
        4. Compute original session duration.
        5. Persist and return the new SessionReplay.
        """
        records = await self._load_ordered_events(
            create.tenant_id, create.original_session_id
        )

        agent_id = create.agent_id or (records[0].agent_id if records else "unknown")
        name = create.name or f"Replay of {create.original_session_id}"

        started_at = records[0].timestamp if records else None
        ended_at = records[-1].timestamp if records else None
        duration = (
            (ended_at - started_at).total_seconds()
            if started_at and ended_at
            else None
        )

        replay_log = [
            {
                "seq": i,
                "event_id": str(r.event_id),
                "event_type": r.event_type,
                "timestamp": r.timestamp.isoformat(),
                "elapsed_seconds": (
                    (r.timestamp - started_at).total_seconds()
                    if started_at
                    else 0.0
                ),
            }
            for i, r in enumerate(records)
        ]

        replay = SessionReplay(
            tenant_id=create.tenant_id,
            original_session_id=create.original_session_id,
            agent_id=agent_id,
            name=name,
            status="pending",
            total_events=len(records),
            current_position=0,
            speed_factor=create.speed_factor,
            original_started_at=started_at,
            original_ended_at=ended_at,
            original_duration_seconds=duration,
            replay_log=replay_log,
            context_window={},
        )
        self._session.add(replay)
        await self._session.commit()
        return replay

    async def get(self, replay_id: UUID) -> SessionReplay:
        result = await self._session.execute(
            select(SessionReplay).where(SessionReplay.id == replay_id)
        )
        replay = result.scalar_one_or_none()
        if replay is None:
            raise NotFoundError(f"SessionReplay {replay_id} not found")
        return replay

    async def list_for_tenant(
        self,
        tenant_id: str,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SessionReplay]:
        stmt = select(SessionReplay).where(SessionReplay.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(SessionReplay.status == status)
        stmt = stmt.order_by(SessionReplay.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    async def get_frames(self, replay_id: UUID) -> list[ReplayFrame]:
        """Return the ordered frame index built at create-time."""
        replay = await self.get(replay_id)
        frames: list[ReplayFrame] = []
        for frame in replay.replay_log:
            frames.append(
                ReplayFrame(
                    sequence_num=frame["seq"],
                    event_id=frame["event_id"],
                    event_type=frame["event_type"],
                    timestamp=datetime.fromisoformat(frame["timestamp"]),
                    elapsed_seconds=frame["elapsed_seconds"],
                    payload_summary={},  # full payloads not stored in log; use get_state_at
                )
            )
        return frames

    async def get_state_at(
        self, replay_id: UUID, position: int
    ) -> AccumulatedState:
        """Reconstruct agent state by folding over events up to *position*.

        Returns an :class:`AccumulatedState` that answers: "What did the agent
        know, what tools were in flight, and what warnings had fired?"

        Complexity: O(position) — events are loaded once and iterated linearly.
        """
        replay = await self.get(replay_id)
        records = await self._load_ordered_events(
            replay.tenant_id, replay.original_session_id
        )

        position = max(0, min(position, len(records)))
        subset = records[:position]

        # --- accumulate ---
        memory_writes: list[dict] = []
        rolled_back_ids: set[str] = set()
        tool_calls_open: list[str] = []
        tool_calls_closed: set[str] = set()
        alerts: list[str] = []
        interventions: list[str] = []
        event_type_counts: dict[str, int] = {}

        for r in subset:
            et = r.event_type
            event_type_counts[et] = event_type_counts.get(et, 0) + 1

            if et == "memory_write_approved":
                memory_writes.append(
                    {"event_id": str(r.event_id), "payload": r.payload}
                )
            elif et == "memory_rollback":
                target = (r.payload or {}).get("target_event_id")
                if target:
                    rolled_back_ids.add(str(target))
            elif et == "tool_call_started":
                tool_calls_open.append(str(r.event_id))
            elif et in (
                "tool_call_completed",
                "tool_call_failed",
                "tool_call_blocked",
            ):
                # The SDK convention is parent_event_id points to the starter.
                parent = (r.payload or {}).get("parent_event_id", str(r.event_id))
                tool_calls_closed.add(str(parent))
            elif et == "sentinel_alert_created":
                alerts.append(
                    (r.payload or {}).get("message", str(r.event_id))
                )
            elif et == "intervention_applied":
                interventions.append(
                    (r.payload or {}).get("action", str(r.event_id))
                )

        active_memory = [
            m for m in memory_writes if m["event_id"] not in rolled_back_ids
        ]
        active_tools = [t for t in tool_calls_open if t not in tool_calls_closed]

        context_events = [
            {
                "seq": i,
                "event_type": r.event_type,
                "timestamp": r.timestamp.isoformat(),
                "payload_summary": _payload_summary(r.payload or {}),
            }
            for i, r in enumerate(
                subset[-_CONTEXT_WINDOW_SIZE:],
                start=max(0, position - _CONTEXT_WINDOW_SIZE),
            )
        ]

        steps_started = event_type_counts.get("agent_step_started", 0)
        steps_completed = event_type_counts.get("agent_step_completed", 0)
        current_step = max(0, steps_started - steps_completed)

        return AccumulatedState(
            position=position,
            total_events=len(records),
            context_window=context_events,
            memory=active_memory,
            active_tool_calls=active_tools,
            sentinel_alerts=alerts,
            interventions=interventions,
            event_type_counts=event_type_counts,
            current_agent_step=current_step,
        )

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    async def step(self, replay_id: UUID) -> ReplayFrame | None:
        """Advance replay by one frame; return the newly active frame or None if complete."""
        replay = await self.get(replay_id)

        if replay.current_position >= replay.total_events:
            replay.status = "completed"
            await self._session.commit()
            return None

        frame_dict = replay.replay_log[replay.current_position]
        replay.current_position += 1
        replay.status = "running"

        # Update persisted context_window snapshot for this position.
        state = await self.get_state_at(replay_id, replay.current_position)
        replay.context_window = state.model_dump()

        if replay.current_position >= replay.total_events:
            replay.status = "completed"

        await self._session.commit()

        return ReplayFrame(
            sequence_num=frame_dict["seq"],
            event_id=frame_dict["event_id"],
            event_type=frame_dict["event_type"],
            timestamp=datetime.fromisoformat(frame_dict["timestamp"]),
            elapsed_seconds=frame_dict["elapsed_seconds"],
            payload_summary={},
        )

    async def run(
        self,
        replay_id: UUID,
        *,
        audit_service: object | None = None,
    ) -> SessionReplay:
        """Execute the full LangGraph replay workflow and persist the result.

        Delegates to :func:`~langgraph_workflows.replay.graph.build_replay_graph`
        which loads, validates, walks, and summarises all events in one pass.
        """
        from langgraph_workflows.replay.graph import build_replay_graph

        replay = await self.get(replay_id)
        replay.status = "running"
        await self._session.commit()

        # Build a lightweight query-compatible proxy.
        query_proxy = _SessionQueryProxy(self._session, replay.tenant_id)
        graph = build_replay_graph(query_proxy, audit_service=audit_service)

        initial: dict = {
            "tenant_id": replay.tenant_id,
            "session_id": replay.original_session_id,
            "agent_id": replay.agent_id,
            "events": [],
            "replayed_count": 0,
            "skipped_count": 0,
            "replay_log": [],
            "has_agent_started": False,
            "has_agent_completed": False,
            "error": None,
            "completed": False,
        }

        try:
            final = await graph.ainvoke(initial)
            replay.status = "completed" if final.get("completed") else "failed"
            replay.current_position = replay.total_events
            replay.context_window = {
                "replayed_count": final.get("replayed_count", 0),
                "skipped_count": final.get("skipped_count", 0),
                "has_agent_started": final.get("has_agent_started", False),
                "has_agent_completed": final.get("has_agent_completed", False),
                "replay_log": final.get("replay_log", []),
                "completed_at": datetime.now(UTC).isoformat(),
            }
        except Exception as exc:
            replay.status = "failed"
            replay.context_window = {"error": str(exc)}

        await self._session.commit()
        return replay

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _load_ordered_events(
        self, tenant_id: str, session_id: str
    ) -> list[EventRecord]:
        """Load all EventRecords for a session, ordered by timestamp ascending."""
        result = await self._session.execute(
            select(EventRecord)
            .where(
                EventRecord.tenant_id == tenant_id,
                EventRecord.session_id == session_id,
            )
            .order_by(EventRecord.timestamp.asc(), EventRecord.created_at.asc())
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Thin proxy so the LangGraph workflow's query_service.list_events() call works
# ---------------------------------------------------------------------------


class _SessionQueryProxy:
    """Wraps AsyncSession to satisfy the list_events() contract expected by the graph."""

    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def list_events(self, filters: object) -> list[EventRecord]:
        from common.schemas.query import EventFilter

        f: EventFilter = filters  # type: ignore[assignment]
        result = await self._session.execute(
            select(EventRecord)
            .where(
                EventRecord.tenant_id == f.tenant_id,
                EventRecord.session_id == f.session_id,
            )
            .order_by(EventRecord.timestamp.asc())
            .limit(f.limit or 500)
        )
        return list(result.scalars().all())
