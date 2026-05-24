"""LangGraph workflow: automated drift analysis with optional audit recording."""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


class DriftAnalysisState(TypedDict):
    tenant_id: str
    agent_id: str
    lookback_hours: int
    drift_score: float | None
    severity: str | None
    deviations_count: int
    alert_created: bool
    audit_entry_id: str | None
    error: str | None


def build_drift_analysis_graph(
    drift_service: Any,
    audit_service: Any | None = None,
) -> Any:
    """Build a compiled drift analysis StateGraph.

    Nodes:
      analyze_drift   — calls DriftDetectionService.analyze(); populates score/severity.
      record_finding  — (conditional) writes an AuditEntry when severity >= medium.
    """

    async def analyze_drift(state: DriftAnalysisState) -> dict[str, Any]:
        from common.schemas.drift import AnalyzeRequest

        try:
            request = AnalyzeRequest(
                tenant_id=state["tenant_id"],
                agent_id=state["agent_id"],
                lookback_hours=state.get("lookback_hours") or 1,
            )
            report = await drift_service.analyze(request)
            return {
                "drift_score": report.drift_score.score,
                "severity": report.drift_score.severity,
                "deviations_count": len(report.drift_score.deviations),
                "alert_created": report.alert_created,
                "error": None,
            }
        except Exception as exc:
            return {
                "drift_score": None,
                "severity": "none",
                "deviations_count": 0,
                "alert_created": False,
                "error": str(exc),
            }

    async def record_finding(state: DriftAnalysisState) -> dict[str, Any]:
        if audit_service is None:
            return {"audit_entry_id": None}
        from common.schemas.audit_log import AuditEntryCreate

        score = state.get("drift_score") or 0.0
        try:
            entry = await audit_service.record(
                AuditEntryCreate(
                    tenant_id=state["tenant_id"],
                    actor_email="system",
                    action="drift_detected",
                    resource_type="agent",
                    resource_id=state["agent_id"],
                    summary=(
                        f"Drift detected for agent {state['agent_id']}: "
                        f"score={score:.4f} severity={state['severity']}"
                    ),
                    extra={
                        "drift_score": score,
                        "severity": state.get("severity"),
                        "deviations_count": state.get("deviations_count", 0),
                    },
                )
            )
            return {"audit_entry_id": str(entry.id)}
        except Exception as exc:
            return {"audit_entry_id": None, "error": str(exc)}

    def _route_after_analysis(state: DriftAnalysisState) -> str:
        if state.get("error"):
            return END
        if state.get("severity") in ("medium", "high", "critical"):
            return "record_finding"
        return END

    graph: StateGraph = StateGraph(DriftAnalysisState)
    graph.add_node("analyze_drift", analyze_drift)
    graph.add_node("record_finding", record_finding)
    graph.add_edge(START, "analyze_drift")
    graph.add_conditional_edges("analyze_drift", _route_after_analysis)
    graph.add_edge("record_finding", END)
    return graph.compile()
