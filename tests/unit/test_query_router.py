"""Module 6 — Query router tests."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from common.audit.integrity import IntegrityReport, IntegrityStatus, RecordIntegrity
from common.exceptions import NotFoundError
from common.models.event import EventRecord
from common.schemas.validators import compute_payload_hash
from services.query.deps import get_query_service
from services.query.router import router
from services.query.service import EventQueryService


def _make_record(tenant_id: str = "tenant-acme") -> EventRecord:
    p = {"step": "test"}
    return EventRecord(
        id=uuid4(),
        event_id=uuid4(),
        trace_id=uuid4(),
        session_id="sess-1",
        tenant_id=tenant_id,
        agent_id="agent-1",
        agent_version="1.0.0",
        event_type="agent_started",
        environment="dev",
        timestamp=datetime.now(UTC),
        client_timestamp=datetime.now(UTC),
        schema_version="1.0",
        payload=p,
        raw_event={},
        payload_hash=compute_payload_hash(p),
    )


def _make_mock_service() -> MagicMock:
    svc = MagicMock(spec=EventQueryService)
    svc.list_events = AsyncMock(return_value=[])
    svc.count_events = AsyncMock(return_value=0)
    svc.get_event = AsyncMock(side_effect=NotFoundError("not found"))
    svc.verify_integrity = AsyncMock(
        return_value=IntegrityReport(
            tenant_id="tenant-acme", total_checked=0, passed=0, failed=0
        )
    )
    return svc


@pytest.fixture()
async def client() -> AsyncGenerator[tuple[AsyncClient, MagicMock], None]:
    app = FastAPI()
    app.include_router(router)
    mock_svc = _make_mock_service()

    async def override() -> EventQueryService:
        return mock_svc  # type: ignore[return-value]

    app.dependency_overrides[get_query_service] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_svc  # type: ignore[misc]


class TestListEvents:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/events", params={"tenant_id": "tenant-acme"})
        assert r.status_code == 200

    async def test_response_shape(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/events", params={"tenant_id": "tenant-acme"})
        body = r.json()
        assert "events" in body
        assert "total" in body
        assert "limit" in body
        assert "offset" in body

    async def test_returns_events_from_service(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        records = [_make_record(), _make_record()]
        mock_svc.list_events = AsyncMock(return_value=records)
        mock_svc.count_events = AsyncMock(return_value=2)
        r = await ac.get("/v1/events", params={"tenant_id": "tenant-acme"})
        assert len(r.json()["events"]) == 2

    async def test_missing_tenant_id_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get("/v1/events")
        assert r.status_code == 422

    async def test_limit_and_offset_reflected_in_response(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get(
            "/v1/events", params={"tenant_id": "t", "limit": 10, "offset": 20}
        )
        body = r.json()
        assert body["limit"] == 10
        assert body["offset"] == 20


class TestGetEvent:
    async def test_returns_404_for_missing_event(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get(f"/v1/events/{uuid4()}")
        assert r.status_code == 404

    async def test_returns_200_for_existing_event(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        record = _make_record()
        mock_svc.get_event = AsyncMock(return_value=record)
        r = await ac.get(f"/v1/events/{record.event_id}")
        assert r.status_code == 200

    async def test_response_contains_event_id(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        record = _make_record()
        mock_svc.get_event = AsyncMock(return_value=record)
        r = await ac.get(f"/v1/events/{record.event_id}")
        assert r.json()["event_id"] == str(record.event_id)

    async def test_invalid_uuid_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get("/v1/events/not-a-uuid")
        assert r.status_code == 422


class TestVerifyIntegrity:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/audit/verify", params={"tenant_id": "tenant-acme"})
        assert r.status_code == 200

    async def test_response_shape(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/audit/verify", params={"tenant_id": "tenant-acme"})
        body = r.json()
        assert "is_clean" in body
        assert "total_checked" in body
        assert "passed" in body
        assert "failed" in body
        assert "records" in body

    async def test_missing_tenant_id_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get("/v1/audit/verify")
        assert r.status_code == 422

    async def test_returns_is_clean_true_for_valid_records(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        record = _make_record()
        mock_svc.verify_integrity = AsyncMock(
            return_value=IntegrityReport(
                tenant_id="tenant-acme",
                total_checked=1,
                passed=1,
                failed=0,
                records=[
                    RecordIntegrity(
                        record_id=str(record.id),
                        event_id=str(record.event_id),
                        status=IntegrityStatus.ok,
                        stored_hash=record.payload_hash,
                        computed_hash=record.payload_hash or "",
                    )
                ],
            )
        )
        r = await ac.get("/v1/audit/verify", params={"tenant_id": "tenant-acme"})
        body = r.json()
        assert body["is_clean"] is True
        assert body["total_checked"] == 1
        assert len(body["records"]) == 1
