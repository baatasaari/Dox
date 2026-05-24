"""Module 17 — Agent SDK: DoxClient tests."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dox_sdk.builder import EventBuilder
from dox_sdk.client import DoxClient
from dox_sdk.result import BatchEmitResult, EmitResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_http(
    *,
    status_code: int = 202,
    body: dict[str, Any] | None = None,
    raise_exc: Exception | None = None,
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = body or {"event_id": str(uuid4()), "status": "accepted"}

    http = MagicMock()
    if raise_exc:
        http.post = AsyncMock(side_effect=raise_exc)
    else:
        http.post = AsyncMock(return_value=response)
    http.aclose = AsyncMock()
    return http


def _make_event() -> Any:
    return EventBuilder("acme", "test-agent", "1.0").agent_started()


def _client(http: MagicMock, *, raise_on_error: bool = False) -> DoxClient:
    return DoxClient(
        "http://dox.test",
        "token-abc",
        raise_on_error=raise_on_error,
        http_client=http,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestInit:
    def test_strips_trailing_slash_from_base_url(self) -> None:
        c = DoxClient("http://dox.test/", "tok", http_client=_mock_http())
        assert c._base_url == "http://dox.test"

    def test_default_timeout_is_five_seconds(self) -> None:
        c = DoxClient("http://x", "tok", http_client=_mock_http())
        assert c._timeout == 5.0

    def test_raise_on_error_defaults_to_false(self) -> None:
        c = DoxClient("http://x", "tok", http_client=_mock_http())
        assert c._raise_on_error is False


# ---------------------------------------------------------------------------
# emit — success
# ---------------------------------------------------------------------------


class TestEmitSuccess:
    async def test_returns_emit_result(self) -> None:
        event_id = uuid4()
        http = _mock_http(body={"event_id": str(event_id), "status": "accepted"})
        result = await _client(http).emit(_make_event())
        assert isinstance(result, EmitResult)

    async def test_success_true_on_202(self) -> None:
        http = _mock_http(status_code=202)
        result = await _client(http).emit(_make_event())
        assert result.success is True

    async def test_success_true_on_200(self) -> None:
        http = _mock_http(status_code=200)
        result = await _client(http).emit(_make_event())
        assert result.success is True

    async def test_event_id_parsed(self) -> None:
        eid = uuid4()
        http = _mock_http(body={"event_id": str(eid), "status": "accepted"})
        result = await _client(http).emit(_make_event())
        assert result.event_id == eid

    async def test_posts_to_correct_url(self) -> None:
        http = _mock_http()
        await _client(http).emit(_make_event())
        url = http.post.call_args[0][0]
        assert url == "http://dox.test/v1/events"

    async def test_authorization_header_sent(self) -> None:
        http = _mock_http()
        await _client(http).emit(_make_event())
        headers = http.post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer token-abc"

    async def test_status_code_in_result(self) -> None:
        http = _mock_http(status_code=202)
        result = await _client(http).emit(_make_event())
        assert result.status_code == 202


# ---------------------------------------------------------------------------
# emit — failure
# ---------------------------------------------------------------------------


class TestEmitFailure:
    async def test_http_error_returns_failed_result_by_default(self) -> None:
        http = _mock_http(status_code=500)
        result = await _client(http).emit(_make_event())
        assert result.success is False
        assert result.error == "HTTP 500"

    async def test_http_error_raises_when_raise_on_error_true(self) -> None:
        http = _mock_http(status_code=500)
        with pytest.raises(RuntimeError, match="HTTP 500"):
            await _client(http, raise_on_error=True).emit(_make_event())

    async def test_network_exception_returns_failed_result(self) -> None:
        http = _mock_http(raise_exc=ConnectionError("refused"))
        result = await _client(http).emit(_make_event())
        assert result.success is False
        assert "refused" in (result.error or "")

    async def test_network_exception_raises_when_raise_on_error_true(self) -> None:
        http = _mock_http(raise_exc=ConnectionError("refused"))
        with pytest.raises(ConnectionError):
            await _client(http, raise_on_error=True).emit(_make_event())

    async def test_timeout_forwarded_to_http(self) -> None:
        http = _mock_http()
        c = DoxClient("http://x", "tok", timeout=2.5, http_client=http)  # type: ignore[arg-type]
        await c.emit(_make_event())
        assert http.post.call_args[1]["timeout"] == 2.5


# ---------------------------------------------------------------------------
# emit_batch
# ---------------------------------------------------------------------------


class TestEmitBatch:
    async def test_empty_list_returns_success_immediately(self) -> None:
        http = _mock_http()
        result = await _client(http).emit_batch([])
        assert result.success is True
        assert result.accepted == 0
        http.post.assert_not_called()

    async def test_posts_to_batch_url(self) -> None:
        http = _mock_http(
            body={"accepted": 2, "event_ids": [str(uuid4()), str(uuid4())], "rejected": 0}
        )
        b = EventBuilder("acme", "ag", "1.0")
        await _client(http).emit_batch([b.agent_started(), b.agent_completed()])
        url = http.post.call_args[0][0]
        assert url == "http://dox.test/v1/events/batch"

    async def test_returns_accepted_count(self) -> None:
        eids = [str(uuid4()), str(uuid4()), str(uuid4())]
        http = _mock_http(body={"accepted": 3, "event_ids": eids, "rejected": 0})
        b = EventBuilder("acme", "ag", "1.0")
        events = [b.agent_started(), b.tool_call_started("t", {}), b.agent_completed()]
        result = await _client(http).emit_batch(events)
        assert result.accepted == 3
        assert len(result.event_ids) == 3

    async def test_batch_failure_returns_failed_result(self) -> None:
        http = _mock_http(status_code=503)
        result = await _client(http).emit_batch([_make_event()])
        assert result.success is False

    async def test_batch_returns_batch_emit_result(self) -> None:
        http = _mock_http(body={"accepted": 1, "event_ids": [str(uuid4())], "rejected": 0})
        result = await _client(http).emit_batch([_make_event()])
        assert isinstance(result, BatchEmitResult)


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    async def test_injected_client_not_closed_on_exit(self) -> None:
        # Externally-injected clients are not owned — DoxClient must not close them.
        http = _mock_http()
        async with DoxClient(
            "http://x", "tok", http_client=http  # type: ignore[arg-type]
        ) as client:
            await client.emit(_make_event())
        http.aclose.assert_not_awaited()

    async def test_returns_client_from_enter(self) -> None:
        http = _mock_http()
        async with DoxClient("http://x", "tok", http_client=http) as client:  # type: ignore[arg-type]
            assert isinstance(client, DoxClient)

    async def test_internally_created_client_closed_on_exit(self) -> None:
        # When no http_client is injected, DoxClient owns and must close it.
        closed: list[bool] = []
        mock_http = _mock_http()
        mock_http.aclose = AsyncMock(side_effect=lambda: closed.append(True))

        client = DoxClient("http://x", "tok")
        client._http = mock_http  # type: ignore[assignment]
        client._owned_client = True
        await client.close()
        assert closed == [True]
