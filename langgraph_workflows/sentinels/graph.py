"""LangGraph workflow: automated sentinel alert response orchestration."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


class SentinelResponseState(TypedDict):
    alert_id: str
    tenant_id: str
    alert_severity: str | None
    alert_type: str | None
    alert_message: str | None
    agent_id: str | None
    matched_policy_id: str | None
    action_taken: str | None
    audit_entry_id: str | None
    resolved: bool
    error: str | None


def build_sentinel_response_graph(
    sentinel_service: Any,
    audit_service: Any,
) -> Any:
    """Build a compiled sentinel-response StateGraph.

    Nodes:
      load_alert           — fetches the SentinelAlert.
      find_policy          — finds the first active Policy matching the alert type.
      execute_action       — resolves the alert using the policy's action.
      resolve_with_default — resolves with InterventionAction.warn when no policy matched.
      record_outcome       — writes an AuditEntry summarising the automated response.

    Routing:
      load_alert  → find_policy (success) | END (error)
      find_policy → execute_action (policy found) | resolve_with_default (no policy)
                  → record_outcome on error too (so we always audit what happened)
      execute_action / resolve_with_default → record_outcome → END
    """

    async def load_alert(state: SentinelResponseState) -> dict[str, Any]:
        try:
            alert = await sentinel_service.get_alert(UUID(state["alert_id"]))
            return {
                "alert_severity": str(alert.severity),
                "alert_type": str(alert.sentinel_type),
                "alert_message": alert.message,
                "agent_id": alert.agent_id,
                "error": None,
            }
        except Exception as exc:
            return {"error": str(exc)}

    async def find_policy(state: SentinelResponseState) -> dict[str, Any]:
        try:
            policies = await sentinel_service.list_policies(
                tenant_id=state["tenant_id"],
                active_only=True,
            )
            alert_type = state.get("alert_type") or ""
            matching = [p for p in policies if str(p.sentinel_type) == alert_type]
            if matching:
                policy = matching[0]
                return {
                    "matched_policy_id": str(policy.id),
                    "action_taken": str(policy.action),
                }
            return {"matched_policy_id": None, "action_taken": None}
        except Exception as exc:
            return {"error": str(exc), "matched_policy_id": None, "action_taken": None}

    async def execute_action(state: SentinelResponseState) -> dict[str, Any]:
        from common.schemas.enums import InterventionAction

        try:
            action = InterventionAction(state.get("action_taken") or "warn")
            await sentinel_service.resolve_alert(UUID(state["alert_id"]), action)
            return {"resolved": True, "error": None}
        except Exception as exc:
            return {"resolved": False, "error": str(exc)}

    async def resolve_with_default(state: SentinelResponseState) -> dict[str, Any]:
        from common.schemas.enums import InterventionAction

        try:
            await sentinel_service.resolve_alert(
                UUID(state["alert_id"]), InterventionAction.warn
            )
            return {
                "resolved": True,
                "action_taken": str(InterventionAction.warn),
            }
        except Exception as exc:
            return {"resolved": False, "error": str(exc)}

    async def record_outcome(state: SentinelResponseState) -> dict[str, Any]:
        from common.schemas.audit_log import AuditEntryCreate

        try:
            entry = await audit_service.record(
                AuditEntryCreate(
                    tenant_id=state["tenant_id"],
                    actor_email="system",
                    action="sentinel_response_applied",
                    resource_type="sentinel_alert",
                    resource_id=state["alert_id"],
                    summary=(
                        f"Automated sentinel response for alert {state['alert_id']}: "
                        f"action={state.get('action_taken') or 'none'}"
                    ),
                    extra={
                        "alert_severity": state.get("alert_severity"),
                        "alert_type": state.get("alert_type"),
                        "policy_id": state.get("matched_policy_id"),
                        "action_taken": state.get("action_taken"),
                        "resolved": state.get("resolved", False),
                    },
                )
            )
            return {"audit_entry_id": str(entry.id)}
        except Exception as exc:
            return {"error": str(exc)}

    def _route_after_load(state: SentinelResponseState) -> str:
        return END if state.get("error") else "find_policy"

    def _route_after_policy(state: SentinelResponseState) -> str:
        if state.get("matched_policy_id"):
            return "execute_action"
        return "resolve_with_default"

    graph: StateGraph = StateGraph(SentinelResponseState)
    graph.add_node("load_alert", load_alert)
    graph.add_node("find_policy", find_policy)
    graph.add_node("execute_action", execute_action)
    graph.add_node("resolve_with_default", resolve_with_default)
    graph.add_node("record_outcome", record_outcome)
    graph.add_edge(START, "load_alert")
    graph.add_conditional_edges("load_alert", _route_after_load)
    graph.add_conditional_edges("find_policy", _route_after_policy)
    graph.add_edge("execute_action", "record_outcome")
    graph.add_edge("resolve_with_default", "record_outcome")
    graph.add_edge("record_outcome", END)
    return graph.compile()
