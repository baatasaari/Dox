"""Module 3 — Ingestion: HTTP route tests."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from common.adapters.event_bus import InMemoryEventBusAdapter
from common.adapters.metrics import InMemoryMetricsAdapter
from services.ingestion.deps import get_ingestion_service
from services.ingestion.router import router
from services.ingestion.service import IngestionService


def _valid_event_dict() -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "event_id": str(uuid4()),
        "trace_id": str(uuid4()),
        "session_id": "sess-1",
        "tenant_id": "tenant-acme",
        "agent_id": "agent-1",
        "agent_version": "1.0.0",
        "event_type": "agent_started",
        "environment": "dev",
        "timestamp": now,
        "client_timestamp": now,
        "correlation_id": "corr-1",
        "payload": {"step": "init"},
    }


@pytest.fixture()
def mock_session() -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock(return_value=None)
    return session


@pytest.fixture()
def event_bus() -> InMemoryEventBusAdapter:
    return InMemoryEventBusAdapter()


@pytest.fixture()
def metrics() -> InMemoryMetricsAdapter:
    return InMemoryMetricsAdapter()


@pytest.fixture()
async def client(
    mock_session: MagicMock,
    event_bus: InMemoryEventBusAdapter,
    metrics: InMemoryMetricsAdapter,
) -> AsyncGenerator[AsyncClient, None]:
    app = FastAPI()
    app.include_router(router)

    @app.get("/healthz", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    async def override() -> IngestionService:
        return IngestionService(mock_session, event_bus, metrics)  # type: ignore[arg-type]

    app.dependency_overrides[get_ingestion_service] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestIngestEndpoint:
    async def test_valid_event_returns_202(self, client: AsyncClient) -> None:
        response = await client.post("/v1/events", json=_valid_event_dict())
        assert response.status_code == 202

    async def test_response_body_contains_event_id(self, client: AsyncClient) -> None:
        payload = _valid_event_dict()
        response = await client.post("/v1/events", json=payload)
        body = response.json()
        assert body["event_id"] == payload["event_id"]

    async def test_response_status_is_accepted(self, client: AsyncClient) -> None:
        response = await client.post("/v1/events", json=_valid_event_dict())
        assert response.json()["status"] == "accepted"

    async def test_missing_required_field_returns_422(self, client: AsyncClient) -> None:
        bad = _valid_event_dict()
        del bad["tenant_id"]
        response = await client.post("/v1/events", json=bad)
        assert response.status_code == 422

    async def test_invalid_event_type_returns_422(self, client: AsyncClient) -> None:
        bad = _valid_event_dict()
        bad["event_type"] = "made_up_type"
        response = await client.post("/v1/events", json=bad)
        assert response.status_code == 422

    async def test_extra_unknown_field_returns_422(self, client: AsyncClient) -> None:
        bad = _valid_event_dict()
        bad["surprise"] = "value"
        response = await client.post("/v1/events", json=bad)
        assert response.status_code == 422

    async def test_malformed_json_returns_422(self, client: AsyncClient) -> None:
        response = await client.post(
            "/v1/events",
            content=b"{not valid json}",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422

    async def test_ingest_publishes_event_to_bus(
        self, client: AsyncClient, event_bus: InMemoryEventBusAdapter
    ) -> None:
        await client.post("/v1/events", json=_valid_event_dict())
        assert len(event_bus.get_events("dox.events.ingested")) == 1


class TestBatchIngestEndpoint:
    async def test_valid_batch_returns_202(self, client: AsyncClient) -> None:
        body = {"events": [_valid_event_dict() for _ in range(3)]}
        response = await client.post("/v1/events/batch", json=body)
        assert response.status_code == 202

    async def test_response_accepted_count_matches_input(self, client: AsyncClient) -> None:
        events = [_valid_event_dict() for _ in range(3)]
        response = await client.post("/v1/events/batch", json={"events": events})
        assert response.json()["accepted"] == 3

    async def test_response_event_ids_count_matches_input(self, client: AsyncClient) -> None:
        events = [_valid_event_dict() for _ in range(2)]
        response = await client.post("/v1/events/batch", json={"events": events})
        assert len(response.json()["event_ids"]) == 2

    async def test_empty_batch_returns_422(self, client: AsyncClient) -> None:
        response = await client.post("/v1/events/batch", json={"events": []})
        assert response.status_code == 422

    async def test_oversized_batch_returns_422(self, client: AsyncClient) -> None:
        events = [_valid_event_dict() for _ in range(101)]
        response = await client.post("/v1/events/batch", json={"events": events})
        assert response.status_code == 422


class TestHealthEndpoint:
    async def test_healthz_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/healthz")
        assert response.status_code == 200

    async def test_healthz_response_body(self, client: AsyncClient) -> None:
        response = await client.get("/healthz")
        assert response.json() == {"status": "ok"}


class TestResponseShape:
    async def test_response_has_received_at_timestamp(self, client: AsyncClient) -> None:
        response = await client.post("/v1/events", json=_valid_event_dict())
        body = response.json()
        assert "received_at" in body
        parsed = datetime.fromisoformat(body["received_at"])
        assert parsed.tzinfo is not None

    async def test_batch_response_rejected_is_zero(self, client: AsyncClient) -> None:
        response = await client.post(
            "/v1/events/batch", json={"events": [_valid_event_dict()]}
        )
        assert response.json()["rejected"] == 0

    async def test_content_type_is_json(self, client: AsyncClient) -> None:
        response = await client.post("/v1/events", json=_valid_event_dict())
        assert "application/json" in response.headers["content-type"]
