"""Module 12 — Tenant Management: HTTP route tests."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from common.exceptions import ConflictError, NotFoundError
from common.models.tenant import Tenant
from services.tenant.deps import get_tenant_service
from services.tenant.router import router
from services.tenant.service import TenantService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tenant(
    *,
    slug: str = "acme",
    name: str = "Acme Corp",
    subscription_tier: str = "starter",
    is_active: bool = True,
) -> Tenant:
    now = datetime.now(UTC)
    return Tenant(
        id=uuid4(),
        slug=slug,
        name=name,
        subscription_tier=subscription_tier,
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )


def _make_mock_service(tenant: Tenant | None = None) -> MagicMock:
    svc = MagicMock(spec=TenantService)
    t = tenant or _make_tenant()
    svc.create = AsyncMock(return_value=t)
    svc.get = AsyncMock(return_value=t)
    svc.get_by_slug = AsyncMock(return_value=t)
    svc.list_tenants = AsyncMock(return_value=[t])
    svc.update = AsyncMock(return_value=t)
    svc.deactivate = AsyncMock(return_value=None)
    svc.activate = AsyncMock(return_value=t)
    return svc


@pytest.fixture()
async def client() -> AsyncGenerator[tuple[AsyncClient, MagicMock], None]:
    app = FastAPI()
    app.include_router(router)
    mock_svc = _make_mock_service()

    async def override() -> TenantService:
        return mock_svc  # type: ignore[return-value]

    app.dependency_overrides[get_tenant_service] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_svc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# POST /v1/tenants
# ---------------------------------------------------------------------------


class TestCreateTenantEndpoint:
    async def test_returns_201(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post("/v1/tenants", json={"slug": "new-org", "name": "New Org"})
        assert r.status_code == 201

    async def test_response_has_tenant_fields(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.post("/v1/tenants", json={"slug": "new-org", "name": "New Org"})
        body = r.json()
        assert "id" in body
        assert "slug" in body
        assert "name" in body
        assert "subscription_tier" in body
        assert "is_active" in body

    async def test_returns_409_on_conflict(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        mock_svc.create = AsyncMock(side_effect=ConflictError("slug taken"))
        r = await ac.post("/v1/tenants", json={"slug": "acme", "name": "Dup"})
        assert r.status_code == 409

    async def test_missing_slug_returns_422(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post("/v1/tenants", json={"name": "No Slug"})
        assert r.status_code == 422

    async def test_missing_name_returns_422(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post("/v1/tenants", json={"slug": "no-name"})
        assert r.status_code == 422

    async def test_calls_service_with_create(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        await ac.post("/v1/tenants", json={"slug": "my-org", "name": "My Org"})
        mock_svc.create.assert_awaited_once()
        req = mock_svc.create.call_args[0][0]
        assert req.slug == "my-org"
        assert req.name == "My Org"


# ---------------------------------------------------------------------------
# GET /v1/tenants
# ---------------------------------------------------------------------------


class TestListTenantsEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/tenants")
        assert r.status_code == 200

    async def test_response_has_list_shape(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/tenants")
        body = r.json()
        assert "tenants" in body
        assert "total" in body

    async def test_total_reflects_count(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        mock_svc.list_tenants = AsyncMock(
            return_value=[_make_tenant(slug=f"org-{i}") for i in range(3)]
        )
        r = await ac.get("/v1/tenants")
        assert r.json()["total"] == 3


# ---------------------------------------------------------------------------
# GET /v1/tenants/by-slug/{slug}
# ---------------------------------------------------------------------------


class TestGetBySlugEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/tenants/by-slug/acme")
        assert r.status_code == 200

    async def test_returns_404_when_not_found(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.get_by_slug = AsyncMock(side_effect=NotFoundError("nope"))
        r = await ac.get("/v1/tenants/by-slug/ghost")
        assert r.status_code == 404

    async def test_calls_service_with_slug(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        await ac.get("/v1/tenants/by-slug/my-tenant")
        mock_svc.get_by_slug.assert_awaited_once_with("my-tenant")


# ---------------------------------------------------------------------------
# GET /v1/tenants/{tenant_id}
# ---------------------------------------------------------------------------


class TestGetTenantEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get(f"/v1/tenants/{uuid4()}")
        assert r.status_code == 200

    async def test_returns_404_when_not_found(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.get = AsyncMock(side_effect=NotFoundError("nope"))
        r = await ac.get(f"/v1/tenants/{uuid4()}")
        assert r.status_code == 404

    async def test_calls_service_with_correct_id(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        tid = uuid4()
        await ac.get(f"/v1/tenants/{tid}")
        mock_svc.get.assert_awaited_once_with(tid)


# ---------------------------------------------------------------------------
# PUT /v1/tenants/{tenant_id}
# ---------------------------------------------------------------------------


class TestUpdateTenantEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.put(f"/v1/tenants/{uuid4()}", json={"name": "Updated"})
        assert r.status_code == 200

    async def test_empty_body_is_valid(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.put(f"/v1/tenants/{uuid4()}", json={})
        assert r.status_code == 200

    async def test_returns_404_when_not_found(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.update = AsyncMock(side_effect=NotFoundError("nope"))
        r = await ac.put(f"/v1/tenants/{uuid4()}", json={"name": "x"})
        assert r.status_code == 404

    async def test_calls_service_with_update(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        tid = uuid4()
        await ac.put(f"/v1/tenants/{tid}", json={"is_active": False})
        mock_svc.update.assert_awaited_once()
        call_args = mock_svc.update.call_args
        assert call_args[0][0] == tid
        assert call_args[0][1].is_active is False


# ---------------------------------------------------------------------------
# DELETE /v1/tenants/{tenant_id}
# ---------------------------------------------------------------------------


class TestDeactivateTenantEndpoint:
    async def test_returns_204(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.delete(f"/v1/tenants/{uuid4()}")
        assert r.status_code == 204

    async def test_returns_404_when_not_found(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.deactivate = AsyncMock(side_effect=NotFoundError("nope"))
        r = await ac.delete(f"/v1/tenants/{uuid4()}")
        assert r.status_code == 404

    async def test_calls_service_with_id(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        tid = uuid4()
        await ac.delete(f"/v1/tenants/{tid}")
        mock_svc.deactivate.assert_awaited_once_with(tid)


# ---------------------------------------------------------------------------
# POST /v1/tenants/{tenant_id}/activate
# ---------------------------------------------------------------------------


class TestActivateTenantEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(f"/v1/tenants/{uuid4()}/activate")
        assert r.status_code == 200

    async def test_response_shows_active_true(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        active_tenant = _make_tenant(is_active=True)
        mock_svc.activate = AsyncMock(return_value=active_tenant)
        r = await ac.post(f"/v1/tenants/{uuid4()}/activate")
        assert r.json()["is_active"] is True

    async def test_returns_404_when_not_found(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.activate = AsyncMock(side_effect=NotFoundError("nope"))
        r = await ac.post(f"/v1/tenants/{uuid4()}/activate")
        assert r.status_code == 404
