"""Module 17 — Agent SDK: EventBuilder tests."""
from __future__ import annotations

from uuid import UUID

import pytest
from dox_sdk.builder import EventBuilder

from common.schemas.enums import EventType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _builder(**kw: object) -> EventBuilder:
    return EventBuilder(
        tenant_id=str(kw.get("tenant_id", "acme")),
        agent_id=str(kw.get("agent_id", "test-agent")),
        agent_version=str(kw.get("agent_version", "1.0.0")),
    )


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestInit:
    def test_generates_trace_id(self) -> None:
        b = _builder()
        assert isinstance(b.trace_id, UUID)

    def test_generates_session_id_if_not_provided(self) -> None:
        b = _builder()
        assert b.session_id
        UUID(b.session_id)  # must be valid UUID string

    def test_accepts_explicit_session_id(self) -> None:
        b = EventBuilder("t", "a", "1.0", session_id="my-session")
        assert b.session_id == "my-session"

    def test_two_builders_have_different_trace_ids(self) -> None:
        b1 = _builder()
        b2 = _builder()
        assert b1.trace_id != b2.trace_id

    def test_default_environment_is_prod(self) -> None:
        b = _builder()
        event = b.agent_started()
        assert event.environment == "prod"

    def test_custom_environment(self) -> None:
        b = EventBuilder("t", "a", "1.0", environment="staging")
        event = b.agent_started()
        assert event.environment == "staging"


# ---------------------------------------------------------------------------
# Shared fields
# ---------------------------------------------------------------------------


class TestSharedFields:
    def test_trace_id_shared_across_events(self) -> None:
        b = _builder()
        e1 = b.agent_started()
        e2 = b.tool_call_started("tool", {})
        assert e1.trace_id == e2.trace_id

    def test_session_id_shared_across_events(self) -> None:
        b = _builder()
        e1 = b.agent_started()
        e2 = b.agent_completed()
        assert e1.session_id == e2.session_id

    def test_tenant_id_on_every_event(self) -> None:
        b = EventBuilder("corp", "ag", "2.0")
        assert b.agent_started().tenant_id == "corp"

    def test_agent_id_on_every_event(self) -> None:
        b = EventBuilder("t", "my-agent", "1.0")
        assert b.agent_started().agent_id == "my-agent"

    def test_sdk_version_on_every_event(self) -> None:
        b = _builder()
        assert b.agent_started().sdk_version == "0.1.0"

    def test_each_event_has_unique_event_id(self) -> None:
        b = _builder()
        ids = {b.agent_started().event_id for _ in range(5)}
        assert len(ids) == 5


# ---------------------------------------------------------------------------
# Sequence numbers
# ---------------------------------------------------------------------------


class TestSequenceNumbers:
    def test_starts_at_one(self) -> None:
        b = _builder()
        assert b.agent_started().sequence_number == 1

    def test_increments_monotonically(self) -> None:
        b = _builder()
        seqs = [b.agent_started().sequence_number for _ in range(5)]
        assert seqs == [1, 2, 3, 4, 5]

    def test_different_event_types_increment_same_counter(self) -> None:
        b = _builder()
        e1 = b.agent_started()
        e2 = b.tool_call_started("t", {})
        e3 = b.agent_completed()
        assert e1.sequence_number == 1
        assert e2.sequence_number == 2
        assert e3.sequence_number == 3


# ---------------------------------------------------------------------------
# Agent lifecycle events
# ---------------------------------------------------------------------------


class TestAgentLifecycle:
    def test_agent_started(self) -> None:
        e = _builder().agent_started()
        assert e.event_type == EventType.agent_started

    def test_agent_completed(self) -> None:
        e = _builder().agent_completed()
        assert e.event_type == EventType.agent_completed

    def test_agent_failed_includes_error(self) -> None:
        e = _builder().agent_failed("timeout")
        assert e.event_type == EventType.agent_failed
        assert e.payload["error"] == "timeout"

    def test_agent_paused_includes_reason(self) -> None:
        e = _builder().agent_paused("awaiting human review")
        assert e.event_type == EventType.agent_paused
        assert e.payload["reason"] == "awaiting human review"


# ---------------------------------------------------------------------------
# Tool call events
# ---------------------------------------------------------------------------


class TestToolCallEvents:
    def test_tool_call_started_has_tool_name_and_inputs(self) -> None:
        e = _builder().tool_call_started("web_search", {"query": "AI news"})
        assert e.event_type == EventType.tool_call_started
        assert e.payload["tool_name"] == "web_search"
        assert e.payload["inputs"] == {"query": "AI news"}

    def test_tool_call_completed_has_output(self) -> None:
        e = _builder().tool_call_completed("web_search", ["result1", "result2"])
        assert e.event_type == EventType.tool_call_completed
        assert e.payload["output"] == ["result1", "result2"]

    def test_tool_call_failed_has_error(self) -> None:
        e = _builder().tool_call_failed("calculator", "division by zero")
        assert e.event_type == EventType.tool_call_failed
        assert e.payload["error"] == "division by zero"

    def test_tool_call_blocked_has_reason(self) -> None:
        e = _builder().tool_call_blocked("delete_file", "policy violation")
        assert e.event_type == EventType.tool_call_blocked
        assert e.payload["reason"] == "policy violation"

    def test_extra_kwargs_included_in_payload(self) -> None:
        e = _builder().tool_call_started("tool", {}, duration_ms=42)
        assert e.payload["duration_ms"] == 42


# ---------------------------------------------------------------------------
# Model call events
# ---------------------------------------------------------------------------


class TestModelCallEvents:
    def test_model_called_has_model_and_tokens(self) -> None:
        e = _builder().model_called("claude-3", 500)
        assert e.event_type == EventType.model_called
        assert e.payload["model"] == "claude-3"
        assert e.payload["prompt_tokens"] == 500

    def test_model_response_received(self) -> None:
        e = _builder().model_response_received("claude-3", 150)
        assert e.event_type == EventType.model_response_received
        assert e.payload["completion_tokens"] == 150


# ---------------------------------------------------------------------------
# Memory events
# ---------------------------------------------------------------------------


class TestMemoryEvents:
    def test_memory_read(self) -> None:
        e = _builder().memory_read("user_context")
        assert e.event_type == EventType.memory_read
        assert e.payload["key"] == "user_context"

    def test_memory_write_requested(self) -> None:
        e = _builder().memory_write_requested("profile")
        assert e.event_type == EventType.memory_write_requested

    def test_memory_write_approved(self) -> None:
        e = _builder().memory_write_approved("profile")
        assert e.event_type == EventType.memory_write_approved

    def test_memory_write_blocked(self) -> None:
        e = _builder().memory_write_blocked("pii_field", "PII detected")
        assert e.event_type == EventType.memory_write_blocked
        assert e.payload["reason"] == "PII detected"


# ---------------------------------------------------------------------------
# Custom events
# ---------------------------------------------------------------------------


class TestCustomEvents:
    def test_custom_passes_event_type_and_payload(self) -> None:
        e = _builder().custom("rag_query", {"query": "hello", "top_k": 5})
        assert e.event_type == "rag_query"
        assert e.payload["query"] == "hello"

    def test_custom_invalid_event_type_raises(self) -> None:
        with pytest.raises(Exception):
            _builder().custom("not_a_real_event_type", {})
