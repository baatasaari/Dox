"""Module 17 — Agent SDK: end-to-end integration through the full app."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from dox_sdk.builder import EventBuilder
from dox_sdk.client import DoxClient
from dox_sdk.result import BatchEmitResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TENANT = "sdk-test-tenant"
_AGENT = "sdk-test-agent"
_VERSION = "1.0.0"


def _mock_http(
    *,
    status_code: int = 202,
    body: dict[str, Any] | None = None,
    exc: Exception | None = None,
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = body or {"event_id": str(uuid4()), "status": "accepted"}
    http = MagicMock()
    if exc:
        http.post = AsyncMock(side_effect=exc)
    else:
        http.post = AsyncMock(return_value=response)
    http.aclose = AsyncMock()
    return http


# ---------------------------------------------------------------------------
# Builder + Client round-trip
# ---------------------------------------------------------------------------


class TestBuilderClientRoundTrip:
    async def test_emit_agent_started_event(self) -> None:
        http = _mock_http()
        builder = EventBuilder(_TENANT, _AGENT, _VERSION)
        event = builder.agent_started(task="summarise document")
        client = DoxClient("http://dox.test", "tok", http_client=http)  # type: ignore[arg-type]
        result = await client.emit(event)
        assert result.success is True
        body = http.post.call_args[1]["json"]
        assert body["tenant_id"] == _TENANT
        assert body["agent_id"] == _AGENT
        assert body["event_type"] == "agent_started"

    async def test_emit_tool_call_sequence(self) -> None:
        http = _mock_http()
        builder = EventBuilder(_TENANT, _AGENT, _VERSION)
        client = DoxClient("http://dox.test", "tok", http_client=http)  # type: ignore[arg-type]

        events = [
            builder.tool_call_started("web_search", {"q": "latest AI news"}),
            builder.tool_call_completed("web_search", ["result1", "result2"]),
        ]
        for event in events:
            await client.emit(event)

        assert http.post.call_count == 2
        payloads = [call[1]["json"] for call in http.post.call_args_list]
        assert payloads[0]["event_type"] == "tool_call_started"
        assert payloads[1]["event_type"] == "tool_call_completed"

    async def test_all_events_share_trace_id(self) -> None:
        http = _mock_http()
        builder = EventBuilder(_TENANT, _AGENT, _VERSION)
        client = DoxClient("http://dox.test", "tok", http_client=http)  # type: ignore[arg-type]

        events = [
            builder.agent_started(),
            builder.model_called("claude-3", 100),
            builder.model_response_received("claude-3", 50),
            builder.agent_completed(),
        ]
        for e in events:
            await client.emit(e)

        payloads = [call[1]["json"] for call in http.post.call_args_list]
        trace_ids = {p["trace_id"] for p in payloads}
        assert len(trace_ids) == 1

    async def test_sequence_numbers_monotone_in_batch(self) -> None:
        http = _mock_http(
            body={
                "accepted": 3,
                "event_ids": [str(uuid4())] * 3,
                "rejected": 0,
            }
        )
        builder = EventBuilder(_TENANT, _AGENT, _VERSION)
        events = [
            builder.agent_started(),
            builder.tool_call_started("t", {}),
            builder.agent_completed(),
        ]
        client = DoxClient("http://dox.test", "tok", http_client=http)  # type: ignore[arg-type]
        result = await client.emit_batch(events)
        assert result.success is True

        batch_payload = http.post.call_args[1]["json"]
        seqs = [e["sequence_number"] for e in batch_payload["events"]]
        assert seqs == [1, 2, 3]


# ---------------------------------------------------------------------------
# Fire-and-forget safety
# ---------------------------------------------------------------------------


class TestFireAndForgetSafety:
    async def test_network_error_does_not_raise_by_default(self) -> None:
        http = _mock_http(exc=ConnectionError("Dox is down"))
        builder = EventBuilder(_TENANT, _AGENT, _VERSION)
        client = DoxClient("http://dox.test", "tok", http_client=http)  # type: ignore[arg-type]
        result = await client.emit(builder.agent_started())
        assert result.success is False
        assert result.error is not None

    async def test_http_500_does_not_raise_by_default(self) -> None:
        http = _mock_http(status_code=500)
        builder = EventBuilder(_TENANT, _AGENT, _VERSION)
        client = DoxClient("http://dox.test", "tok", http_client=http)  # type: ignore[arg-type]
        result = await client.emit(builder.agent_started())
        assert result.success is False

    async def test_batch_network_error_does_not_raise(self) -> None:
        http = _mock_http(exc=TimeoutError("timeout"))
        builder = EventBuilder(_TENANT, _AGENT, _VERSION)
        client = DoxClient("http://dox.test", "tok", http_client=http)  # type: ignore[arg-type]
        result = await client.emit_batch([builder.agent_started()])
        assert isinstance(result, BatchEmitResult)
        assert result.success is False

    async def test_agent_logic_continues_after_failed_emit(self) -> None:
        http = _mock_http(exc=RuntimeError("network failure"))
        builder = EventBuilder(_TENANT, _AGENT, _VERSION)
        client = DoxClient("http://dox.test", "tok", http_client=http)  # type: ignore[arg-type]

        result1 = await client.emit(builder.agent_started())
        result2 = await client.emit(builder.agent_completed())

        assert result1.success is False
        assert result2.success is False
        assert http.post.call_count == 2


# ---------------------------------------------------------------------------
# Memory and model event round-trips
# ---------------------------------------------------------------------------


class TestMemoryAndModelEvents:
    async def test_memory_write_flow(self) -> None:
        http = _mock_http()
        builder = EventBuilder(_TENANT, _AGENT, _VERSION)
        client = DoxClient("http://dox.test", "tok", http_client=http)  # type: ignore[arg-type]

        await client.emit(builder.memory_write_requested("user_profile", data={"name": "Alice"}))
        await client.emit(builder.memory_write_approved("user_profile"))

        calls = http.post.call_args_list
        types = [c[1]["json"]["event_type"] for c in calls]
        assert types == ["memory_write_requested", "memory_write_approved"]

    async def test_model_call_round_trip(self) -> None:
        http = _mock_http()
        builder = EventBuilder(_TENANT, _AGENT, _VERSION)
        client = DoxClient("http://dox.test", "tok", http_client=http)  # type: ignore[arg-type]

        await client.emit(builder.model_called("claude-sonnet-4-6", 800))
        await client.emit(builder.model_response_received("claude-sonnet-4-6", 200))

        calls = http.post.call_args_list
        req_payload = calls[0][1]["json"]["payload"]
        assert req_payload["model"] == "claude-sonnet-4-6"
        assert req_payload["prompt_tokens"] == 800
