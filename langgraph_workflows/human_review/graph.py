"""LangGraph workflow: human review escalation for sentinel alerts."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


class HumanReviewState(TypedDict):
    alert_id: str
    tenant_id: str
    alert_severity: str | None
    alert_type: str | None
    alert_message: str | None
    reviewer_id: str | None
    # decision supplied on resume: "approve" | "reject" | "escalate"
    decision: str | None
    notes: str | None
    audit_entry_id: str | None
    resolved: bool
    error: str | None


def build_human_review_graph(
    sentinel_service: Any,
    audit_service: Any,
) -> Any:
    """Build a compiled human-review StateGraph.

    Nodes:
      load_alert      — fetches the SentinelAlert from the DB.
      request_review  — creates an AuditEntry recording the review request.
      record_decision — resolves the alert and audits the human decision (when
                        a decision is present in state).

    Routing:
      load_alert      → request_review (on success) | END (on error)
      request_review  → record_decision (if state.decision set) | END (awaiting input)
      record_decision → END
    """

    async def load_alert(state: HumanReviewState) -> dict[str, Any]:
        try:
            alert = await sentinel_service.get_alert(UUID(state["alert_id"]))
            return {
                "alert_severity": str(alert.severity),
                "alert_type": str(alert.sentinel_type),
                "alert_message": alert.message,
                "error": None,
            }
        except Exception as exc:
            return {"error": str(exc)}

    async def request_review(state: HumanReviewState) -> dict[str, Any]:
        from common.schemas.audit_log import AuditEntryCreate

        try:
            entry = await audit_service.record(
                AuditEntryCreate(
                    tenant_id=state["tenant_id"],
                    actor_email="system",
                    action="human_review_requested",
                    resource_type="sentinel_alert",
                    resource_id=state["alert_id"],
                    summary=(
                        f"Human review requested for alert {state['alert_id']}: "
                        f"{state.get('alert_message', '')}"
                    ),
                    extra={
                        "severity": state.get("alert_severity"),
                        "type": state.get("alert_type"),
                        "reviewer_id": state.get("reviewer_id"),
                    },
                )
            )
            return {"audit_entry_id": str(entry.id)}
        except Exception as exc:
            return {"error": str(exc)}

    async def record_decision(state: HumanReviewState) -> dict[str, Any]:
        from common.schemas.audit_log import AuditEntryCreate
        from common.schemas.enums import InterventionAction

        action_map = {
            "approve": InterventionAction.allow,
            "reject": InterventionAction.block_tool_call,
            "escalate": InterventionAction.request_human_review,
        }
        decision = state.get("decision") or "reject"
        action = action_map.get(decision, InterventionAction.warn)
        try:
            await sentinel_service.resolve_alert(UUID(state["alert_id"]), action)
            await audit_service.record(
                AuditEntryCreate(
                    tenant_id=state["tenant_id"],
                    actor_email=state.get("reviewer_id") or "system",
                    action="human_review_completed",
                    resource_type="sentinel_alert",
                    resource_id=state["alert_id"],
                    summary=(
                        f"Human review decision '{decision}' recorded "
                        f"for alert {state['alert_id']}"
                    ),
                    extra={
                        "decision": decision,
                        "notes": state.get("notes"),
                        "action_taken": str(action),
                    },
                )
            )
            return {"resolved": True, "error": None}
        except Exception as exc:
            return {"resolved": False, "error": str(exc)}

    def _route_after_load(state: HumanReviewState) -> str:
        return END if state.get("error") else "request_review"

    def _route_after_request(state: HumanReviewState) -> str:
        if state.get("error"):
            return END
        return "record_decision" if state.get("decision") else END

    graph: StateGraph = StateGraph(HumanReviewState)
    graph.add_node("load_alert", load_alert)
    graph.add_node("request_review", request_review)
    graph.add_node("record_decision", record_decision)
    graph.add_edge(START, "load_alert")
    graph.add_conditional_edges("load_alert", _route_after_load)
    graph.add_conditional_edges("request_review", _route_after_request)
    graph.add_edge("record_decision", END)
    return graph.compile()
