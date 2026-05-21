"""Module 1 — Event Schema: Enum tests."""
from __future__ import annotations

import re

import pytest

from common.schemas.enums import (
    Environment,
    EventType,
    InterventionAction,
    SentinelType,
    Severity,
)


class TestEnvironmentEnum:
    def test_has_exactly_four_values(self) -> None:
        assert len(Environment) == 4

    def test_contains_all_expected_values(self) -> None:
        assert set(e.value for e in Environment) == {"dev", "test", "staging", "prod"}

    def test_values_are_lowercase_strings(self) -> None:
        for member in Environment:
            assert member.value == member.value.lower()
            assert isinstance(member.value, str)

    def test_string_coercion(self) -> None:
        assert Environment("dev") == Environment.dev
        assert Environment("prod") == Environment.prod

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            Environment("production")


class TestEventTypeEnum:
    def test_has_exactly_34_values(self) -> None:
        assert len(EventType) == 34

    def test_all_values_are_snake_case(self) -> None:
        snake_case_pattern = re.compile(r"^[a-z][a-z_]*[a-z]$")
        for member in EventType:
            assert snake_case_pattern.match(member.value), (
                f"EventType.{member.name} value '{member.value}' is not snake_case"
            )

    def test_string_coercion_works_for_every_value(self) -> None:
        for member in EventType:
            assert EventType(member.value) == member

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            EventType("model_started")

    def test_contains_required_lifecycle_events(self) -> None:
        required = {
            "agent_started", "agent_completed", "agent_failed",
            "agent_paused", "agent_resumed", "agent_terminated",
            "model_called", "model_response_received",
            "tool_call_started", "tool_call_completed", "tool_call_failed",
            "memory_read", "memory_write_requested",
            "sentinel_alert_created", "intervention_applied",
        }
        actual = {m.value for m in EventType}
        assert required.issubset(actual), f"Missing: {required - actual}"

    def test_contains_governance_events(self) -> None:
        assert "policy_evaluated" in {m.value for m in EventType}
        assert "intervention_requested" in {m.value for m in EventType}
        assert "consent_checked" in {m.value for m in EventType}

    def test_contains_data_lineage_events(self) -> None:
        assert "rag_query" in {m.value for m in EventType}
        assert "rag_chunk_retrieved" in {m.value for m in EventType}


class TestSeverityEnum:
    def test_has_exactly_four_values(self) -> None:
        assert len(Severity) == 4

    def test_contains_all_expected_values(self) -> None:
        assert set(s.value for s in Severity) == {"low", "medium", "high", "critical"}


class TestSentinelTypeEnum:
    def test_has_exactly_eleven_values(self) -> None:
        assert len(SentinelType) == 11

    def test_contains_all_required_sentinel_types(self) -> None:
        expected = {
            "trajectory", "tool_misuse", "policy_breach", "memory",
            "drift", "injection", "cost_loop", "delegation",
            "bias", "hallucination", "regulatory",
        }
        assert set(s.value for s in SentinelType) == expected


class TestInterventionActionEnum:
    def test_has_exactly_ten_values(self) -> None:
        assert len(InterventionAction) == 10

    def test_contains_all_required_actions(self) -> None:
        expected = {
            "allow", "warn", "redact", "block_tool_call", "pause_agent",
            "request_human_review", "force_safe_response",
            "rollback_memory_write", "isolate_agent", "terminate_execution",
        }
        assert set(a.value for a in InterventionAction) == expected

    def test_block_tool_call_value(self) -> None:
        assert InterventionAction.block_tool_call.value == "block_tool_call"

    def test_terminate_execution_value(self) -> None:
        assert InterventionAction.terminate_execution.value == "terminate_execution"
