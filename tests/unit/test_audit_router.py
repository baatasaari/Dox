"""Module 16 — Audit Trail: HTTP route tests."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from common.exceptions import NotFoundError
from common.models.audit_log import AuditEntry
from services.audit.deps import get_audit_service
from services.audit.router import router
from services.audit.service import AuditService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    *,
    tenant_id: str = "acme",
    action: str = "user.create",
    resource_type: str = "user",
) -> AuditEntry:
    now = datetime.now(UTC)
    e = AuditEntry(
        id=uuid4(),
        tenant_id=tenant_id,
        actor_id=uuid4(),
        actor_email="alice@example.com",
        action=action,
        resource_type=resource_type,
        resource_id=str(uuid4()),
        summary=f"Performed {action} on {resource_type}",
        extra={},
    )
    e.created_at = now  # type: ignore[assignment]
    return e


def _make_mock_service(entry: AuditEntry | None = None) -> MagicMock:
    e = entry or _make_entry()
    svc = MagicMock(spec=AuditService)
    svc.record = AsyncMock(return_value=e)
    svc.get = AsyncMock(return_value=e)
    svc.list_for_tenant = AsyncMock(return_value=[e])
    svc.count_for_tenant = AsyncMock(return_value=1)
    return svc


@pytest.fixture()
async def client() -> AsyncGenerator[tuple[AsyncClient, MagicMock], None]:
    app = FastAPI()
    app.include_router(router)
    mock_svc = _make_mock_service()

    async def override() -> AuditService:
        return mock_svc  # type: ignore[return-value]

    app.dependency_overrides[get_audit_service] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_svc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# POST /v1/audit-log
# ---------------------------------------------------------------------------


class TestRecordEntry:
    async def test_returns_201(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/audit-log",
            json={
                "tenant_id": "acme",
                "actor_email": "alice@example.com",
                "action": "user.create",
                "resource_type": "user",
                "resource_id": str(uuid4()),
                "summary": "Created user alice@example.com",
            },
        )
        assert r.status_code == 201

    async def test_response_has_entry_fields(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/audit-log",
            json={
                "tenant_id": "acme",
                "action": "user.create",
                "resource_type": "user",
                "resource_id": "u-1",
                "summary": "Created user",
            },
        )
        body = r.json()
        assert "id" in body
        assert "tenant_id" in body
        assert "action" in body
        assert "resource_type" in body
        assert "resource_id" in body
        assert "summary" in body
        assert "created_at" in body

    async def test_calls_service_record(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        await ac.post(
            "/v1/audit-log",
            json={
                "tenant_id": "acme",
                "action": "policy.update",
                "resource_type": "policy",
                "resource_id": "p-1",
                "summary": "Updated policy",
            },
        )
        mock_svc.record.assert_awaited_once()

    async def test_missing_action_returns_422(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/audit-log",
            json={"tenant_id": "acme", "resource_type": "user", "resource_id": "u-1"},
        )
        assert r.status_code == 422

    async def test_empty_action_returns_422(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/audit-log",
            json={
                "tenant_id": "acme",
                "action": "",
                "resource_type": "user",
                "resource_id": "u-1",
                "summary": "s",
            },
        )
        assert r.status_code == 422

    async def test_system_actor_email_default(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        await ac.post(
            "/v1/audit-log",
            json={
                "tenant_id": "t",
                "action": "agent.deactivate",
                "resource_type": "agent",
                "resource_id": "ag-1",
                "summary": "Deactivated agent",
            },
        )
        req = mock_svc.record.call_args[0][0]
        assert req.actor_email == "system"


# ---------------------------------------------------------------------------
# GET /v1/audit-log/{tenant_id}
# ---------------------------------------------------------------------------


class TestListEntries:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/audit-log/acme")
        assert r.status_code == 200

    async def test_response_has_list_shape(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/audit-log/acme")
        body = r.json()
        assert "entries" in body
        assert "total" in body
        assert "limit" in body
        assert "offset" in body

    async def test_total_reflects_count(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        entries = [_make_entry() for _ in range(4)]
        mock_svc.list_for_tenant = AsyncMock(return_value=entries)
        mock_svc.count_for_tenant = AsyncMock(return_value=12)
        r = await ac.get("/v1/audit-log/acme")
        assert r.json()["total"] == 12
        assert len(r.json()["entries"]) == 4

    async def test_passes_action_filter(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        await ac.get("/v1/audit-log/acme", params={"action": "user.create"})
        call_kwargs = mock_svc.list_for_tenant.call_args[1]
        assert call_kwargs["action"] == "user.create"

    async def test_passes_resource_type_filter(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        await ac.get("/v1/audit-log/acme", params={"resource_type": "policy"})
        call_kwargs = mock_svc.list_for_tenant.call_args[1]
        assert call_kwargs["resource_type"] == "policy"

    async def test_passes_actor_id_filter(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        actor_id = uuid4()
        await ac.get("/v1/audit-log/acme", params={"actor_id": str(actor_id)})
        call_kwargs = mock_svc.list_for_tenant.call_args[1]
        assert call_kwargs["actor_id"] == actor_id

    async def test_default_limit_is_50(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        await ac.get("/v1/audit-log/acme")
        call_kwargs = mock_svc.list_for_tenant.call_args[1]
        assert call_kwargs["limit"] == 50

    async def test_limit_too_large_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get("/v1/audit-log/acme", params={"limit": 9999})
        assert r.status_code == 422

    async def test_negative_offset_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get("/v1/audit-log/acme", params={"offset": -1})
        assert r.status_code == 422

    async def test_offset_passed_through(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        await ac.get("/v1/audit-log/acme", params={"offset": 20})
        call_kwargs = mock_svc.list_for_tenant.call_args[1]
        assert call_kwargs["offset"] == 20


# ---------------------------------------------------------------------------
# GET /v1/audit-log/{tenant_id}/{entry_id}
# ---------------------------------------------------------------------------


class TestGetEntry:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        entry = _make_entry(tenant_id="acme")
        mock_svc.get = AsyncMock(return_value=entry)
        r = await ac.get(f"/v1/audit-log/acme/{entry.id}")
        assert r.status_code == 200

    async def test_returns_404_when_not_found(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.get = AsyncMock(side_effect=NotFoundError("missing"))
        r = await ac.get(f"/v1/audit-log/acme/{uuid4()}")
        assert r.status_code == 404

    async def test_returns_404_for_wrong_tenant(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        entry = _make_entry(tenant_id="other-tenant")
        mock_svc.get = AsyncMock(return_value=entry)
        r = await ac.get(f"/v1/audit-log/acme/{entry.id}")
        assert r.status_code == 404

    async def test_response_has_all_fields(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        entry = _make_entry(tenant_id="acme")
        mock_svc.get = AsyncMock(return_value=entry)
        r = await ac.get(f"/v1/audit-log/acme/{entry.id}")
        body = r.json()
        for field in ("id", "tenant_id", "actor_email", "action", "resource_type",
                      "resource_id", "summary", "extra", "created_at"):
            assert field in body, f"Missing field: {field}"

    async def test_invalid_uuid_returns_422(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/audit-log/acme/not-a-uuid")
        assert r.status_code == 422
