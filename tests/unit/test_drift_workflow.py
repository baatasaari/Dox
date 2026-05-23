"""Module 18 — LangGraph Workflows: drift analysis graph tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from langgraph_workflows.drift_analysis import DriftAnalysisState, build_drift_analysis_graph

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _initial_state(**overrides: object) -> DriftAnalysisState:
    base: DriftAnalysisState = {
        "tenant_id": "acme",
        "agent_id": "test-agent",
        "lookback_hours": 1,
        "drift_score": None,
        "severity": None,
        "deviations_count": 0,
        "alert_created": False,
        "audit_entry_id": None,
        "error": None,
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


def _drift_report(
    score: float, severity: str, deviations: int = 0, alert: bool = False
) -> MagicMock:
    dev_list = [MagicMock() for _ in range(deviations)]
    report = MagicMock()
    report.drift_score.score = score
    report.drift_score.severity = severity
    report.drift_score.deviations = dev_list
    report.alert_created = alert
    return report


def _drift_service(
    report: MagicMock | None = None, *, raise_exc: Exception | None = None
) -> AsyncMock:
    svc = AsyncMock()
    if raise_exc:
        svc.analyze = AsyncMock(side_effect=raise_exc)
    else:
        svc.analyze = AsyncMock(return_value=report or _drift_report(0.1, "none"))
    return svc


def _audit_service() -> AsyncMock:
    svc = AsyncMock()
    entry = MagicMock()
    entry.id = uuid4()
    svc.record = AsyncMock(return_value=entry)
    return svc


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


class TestGraphCompiles:
    def test_compiles_without_audit_service(self) -> None:
        graph = build_drift_analysis_graph(_drift_service())
        assert graph is not None

    def test_compiles_with_audit_service(self) -> None:
        graph = build_drift_analysis_graph(_drift_service(), _audit_service())
        assert graph is not None


# ---------------------------------------------------------------------------
# Analyze node — success paths
# ---------------------------------------------------------------------------


class TestAnalyzeSuccess:
    async def test_populates_drift_score(self) -> None:
        report = _drift_report(0.42, "medium")
        graph = build_drift_analysis_graph(_drift_service(report))
        result = await graph.ainvoke(_initial_state())
        assert result["drift_score"] == pytest.approx(0.42)

    async def test_populates_severity(self) -> None:
        report = _drift_report(0.8, "high")
        graph = build_drift_analysis_graph(_drift_service(report))
        result = await graph.ainvoke(_initial_state())
        assert result["severity"] == "high"

    async def test_populates_deviations_count(self) -> None:
        report = _drift_report(0.5, "medium", deviations=3)
        graph = build_drift_analysis_graph(_drift_service(report))
        result = await graph.ainvoke(_initial_state())
        assert result["deviations_count"] == 3

    async def test_alert_created_reflects_service_result(self) -> None:
        report = _drift_report(0.7, "high", alert=True)
        graph = build_drift_analysis_graph(_drift_service(report))
        result = await graph.ainvoke(_initial_state())
        assert result["alert_created"] is True

    async def test_no_error_on_success(self) -> None:
        graph = build_drift_analysis_graph(_drift_service(_drift_report(0.1, "none")))
        result = await graph.ainvoke(_initial_state())
        assert result["error"] is None


# ---------------------------------------------------------------------------
# Analyze node — error paths
# ---------------------------------------------------------------------------


class TestAnalyzeError:
    async def test_error_field_set_on_exception(self) -> None:
        svc = _drift_service(raise_exc=RuntimeError("db down"))
        graph = build_drift_analysis_graph(svc)
        result = await graph.ainvoke(_initial_state())
        assert result["error"] == "db down"

    async def test_severity_none_on_exception(self) -> None:
        svc = _drift_service(raise_exc=ValueError("bad"))
        graph = build_drift_analysis_graph(svc)
        result = await graph.ainvoke(_initial_state())
        assert result["severity"] == "none"

    async def test_drift_score_none_on_exception(self) -> None:
        svc = _drift_service(raise_exc=ConnectionError("refused"))
        graph = build_drift_analysis_graph(svc)
        result = await graph.ainvoke(_initial_state())
        assert result["drift_score"] is None


# ---------------------------------------------------------------------------
# Routing — audit recording
# ---------------------------------------------------------------------------


class TestAuditRecording:
    async def test_audit_called_for_medium_severity(self) -> None:
        report = _drift_report(0.45, "medium")
        audit = _audit_service()
        graph = build_drift_analysis_graph(_drift_service(report), audit)
        await graph.ainvoke(_initial_state())
        audit.record.assert_called_once()

    async def test_audit_called_for_high_severity(self) -> None:
        report = _drift_report(0.75, "high")
        audit = _audit_service()
        graph = build_drift_analysis_graph(_drift_service(report), audit)
        await graph.ainvoke(_initial_state())
        audit.record.assert_called_once()

    async def test_audit_not_called_for_none_severity(self) -> None:
        report = _drift_report(0.05, "none")
        audit = _audit_service()
        graph = build_drift_analysis_graph(_drift_service(report), audit)
        await graph.ainvoke(_initial_state())
        audit.record.assert_not_called()

    async def test_audit_not_called_for_low_severity(self) -> None:
        report = _drift_report(0.15, "low")
        audit = _audit_service()
        graph = build_drift_analysis_graph(_drift_service(report), audit)
        await graph.ainvoke(_initial_state())
        audit.record.assert_not_called()

    async def test_audit_not_called_on_analyze_error(self) -> None:
        audit = _audit_service()
        graph = build_drift_analysis_graph(
            _drift_service(raise_exc=RuntimeError("fail")), audit
        )
        await graph.ainvoke(_initial_state())
        audit.record.assert_not_called()

    async def test_audit_entry_id_populated(self) -> None:
        report = _drift_report(0.6, "medium")
        audit = _audit_service()
        graph = build_drift_analysis_graph(_drift_service(report), audit)
        result = await graph.ainvoke(_initial_state())
        assert result["audit_entry_id"] is not None

    async def test_no_audit_service_does_not_raise(self) -> None:
        report = _drift_report(0.9, "high")
        graph = build_drift_analysis_graph(_drift_service(report))
        result = await graph.ainvoke(_initial_state())
        assert result["audit_entry_id"] is None

    async def test_audit_payload_contains_tenant_and_agent(self) -> None:
        report = _drift_report(0.5, "medium")
        audit = _audit_service()
        graph = build_drift_analysis_graph(_drift_service(report), audit)
        await graph.ainvoke(_initial_state(tenant_id="corp", agent_id="my-agent"))
        call_kwargs = audit.record.call_args[0][0]
        assert call_kwargs.tenant_id == "corp"
        assert call_kwargs.resource_id == "my-agent"
        assert call_kwargs.action == "drift_detected"
