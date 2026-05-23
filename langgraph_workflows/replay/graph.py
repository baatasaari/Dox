"""LangGraph workflow: agent session event replay for debugging and audit."""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


class ReplayState(TypedDict):
    tenant_id: str
    session_id: str
    agent_id: str | None
    events: list[dict[str, Any]]
    replayed_count: int
    skipped_count: int
    replay_log: list[str]
    has_agent_started: bool
    has_agent_completed: bool
    error: str | None
    completed: bool


def build_replay_graph(
    query_service: Any,
    audit_service: Any | None = None,
) -> Any:
    """Build a compiled session-replay StateGraph.

    Nodes:
      load_events     — queries EventRecords for the session, sorted by timestamp.
      validate_events — marks whether the session has agent_started / agent_completed.
      replay_events   — walks every event and builds the replay log.
      summarize       — optionally writes an AuditEntry; marks completed=True.

    Routing:
      load_events → validate_events (events found, no error) | END (otherwise)
      validate_events → replay_events → summarize → END
    """

    async def load_events(state: ReplayState) -> dict[str, Any]:
        from common.schemas.query import EventFilter

        try:
            filters = EventFilter(
                tenant_id=state["tenant_id"],
                session_id=state["session_id"],
                agent_id=state.get("agent_id"),
                limit=500,
            )
            records = await query_service.list_events(filters)
            events = [
                {
                    "event_id": str(r.event_id),
                    "event_type": r.event_type,
                    "agent_id": r.agent_id,
                    "timestamp": r.timestamp.isoformat(),
                    "payload": r.payload,
                }
                for r in sorted(records, key=lambda r: r.timestamp)
            ]
            return {"events": events, "error": None}
        except Exception as exc:
            return {"events": [], "error": str(exc)}

    def validate_events(state: ReplayState) -> dict[str, Any]:
        types = {e["event_type"] for e in state.get("events", [])}
        return {
            "has_agent_started": "agent_started" in types,
            "has_agent_completed": (
                "agent_completed" in types or "agent_failed" in types
            ),
        }

    async def replay_events(state: ReplayState) -> dict[str, Any]:
        log: list[str] = []
        replayed = 0
        skipped = 0
        for evt in state.get("events", []):
            try:
                log.append(f"[{evt['event_type']}] {evt['event_id']}")
                replayed += 1
            except Exception as exc:
                log.append(f"[SKIP] {evt.get('event_id', '?')}: {exc}")
                skipped += 1
        return {
            "replayed_count": replayed,
            "skipped_count": skipped,
            "replay_log": log,
        }

    async def summarize(state: ReplayState) -> dict[str, Any]:
        if audit_service is not None:
            from common.schemas.audit_log import AuditEntryCreate

            events = state.get("events", [])
            agent_id = state.get("agent_id") or (
                events[0]["agent_id"] if events else "unknown"
            )
            try:
                await audit_service.record(
                    AuditEntryCreate(
                        tenant_id=state["tenant_id"],
                        actor_email="system",
                        action="replay_completed",
                        resource_type="session",
                        resource_id=state["session_id"],
                        summary=(
                            f"Replay of session {state['session_id']} "
                            f"(agent={agent_id}): "
                            f"{state.get('replayed_count', 0)} replayed, "
                            f"{state.get('skipped_count', 0)} skipped"
                        ),
                        extra={
                            "replayed_count": state.get("replayed_count", 0),
                            "skipped_count": state.get("skipped_count", 0),
                            "has_agent_started": state.get("has_agent_started", False),
                            "has_agent_completed": state.get("has_agent_completed", False),
                        },
                    )
                )
            except Exception:
                pass
        return {"completed": True}

    def _route_after_load(state: ReplayState) -> str:
        if state.get("error") or not state.get("events"):
            return END
        return "validate_events"

    graph: StateGraph = StateGraph(ReplayState)
    graph.add_node("load_events", load_events)
    graph.add_node("validate_events", validate_events)
    graph.add_node("replay_events", replay_events)
    graph.add_node("summarize", summarize)
    graph.add_edge(START, "load_events")
    graph.add_conditional_edges("load_events", _route_after_load)
    graph.add_edge("validate_events", "replay_events")
    graph.add_edge("replay_events", "summarize")
    graph.add_edge("summarize", END)
    return graph.compile()
