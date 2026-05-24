"""Module 14 — User Management: HTTP route tests."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from common.exceptions import ConflictError, NotFoundError
from common.models.user import User
from common.schemas.enums import UserRole
from services.users.deps import get_user_service
from services.users.router import router
from services.users.service import UserService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    *,
    email: str = "alice@example.com",
    tenant_id: str = "acme",
    role: str = UserRole.viewer,
    is_active: bool = True,
) -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid4(),
        email=email,
        hashed_password="hashed",
        tenant_id=tenant_id,
        role=role,
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )


def _make_mock_service(user: User | None = None) -> MagicMock:
    svc = MagicMock(spec=UserService)
    u = user or _make_user()
    svc.create = AsyncMock(return_value=u)
    svc.get = AsyncMock(return_value=u)
    svc.get_by_email = AsyncMock(return_value=u)
    svc.list_for_tenant = AsyncMock(return_value=[u])
    svc.update = AsyncMock(return_value=u)
    svc.deactivate = AsyncMock(return_value=None)
    svc.change_password = AsyncMock(return_value=u)
    return svc


@pytest.fixture()
async def client() -> AsyncGenerator[tuple[AsyncClient, MagicMock], None]:
    app = FastAPI()
    app.include_router(router)
    mock_svc = _make_mock_service()

    async def override() -> UserService:
        return mock_svc  # type: ignore[return-value]

    app.dependency_overrides[get_user_service] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_svc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# POST /v1/users
# ---------------------------------------------------------------------------


class TestCreateUserEndpoint:
    async def test_returns_201(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/users",
            json={"email": "a@b.com", "password": "secret123", "tenant_id": "acme"},
        )
        assert r.status_code == 201

    async def test_response_has_user_fields(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/users",
            json={"email": "a@b.com", "password": "secret123", "tenant_id": "acme"},
        )
        body = r.json()
        assert "id" in body
        assert "email" in body
        assert "tenant_id" in body
        assert "role" in body
        assert "is_active" in body
        assert "hashed_password" not in body

    async def test_returns_409_on_conflict(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        mock_svc.create = AsyncMock(side_effect=ConflictError("dup"))
        r = await ac.post(
            "/v1/users",
            json={"email": "a@b.com", "password": "secret123", "tenant_id": "acme"},
        )
        assert r.status_code == 409

    async def test_short_password_returns_422(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/users",
            json={"email": "a@b.com", "password": "short", "tenant_id": "acme"},
        )
        assert r.status_code == 422

    async def test_missing_email_returns_422(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/users", json={"password": "secret123", "tenant_id": "acme"}
        )
        assert r.status_code == 422

    async def test_calls_service_with_create(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        await ac.post(
            "/v1/users",
            json={"email": "new@x.com", "password": "secret123", "tenant_id": "t1"},
        )
        mock_svc.create.assert_awaited_once()
        req = mock_svc.create.call_args[0][0]
        assert req.email == "new@x.com"
        assert req.tenant_id == "t1"


# ---------------------------------------------------------------------------
# GET /v1/users
# ---------------------------------------------------------------------------


class TestListUsersEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/users", params={"tenant_id": "acme"})
        assert r.status_code == 200

    async def test_response_has_list_shape(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/users", params={"tenant_id": "acme"})
        body = r.json()
        assert "users" in body
        assert "total" in body

    async def test_no_password_in_list_items(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/users", params={"tenant_id": "acme"})
        for item in r.json()["users"]:
            assert "hashed_password" not in item

    async def test_missing_tenant_id_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get("/v1/users")
        assert r.status_code == 422

    async def test_total_reflects_count(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        mock_svc.list_for_tenant = AsyncMock(
            return_value=[_make_user(email=f"u{i}@x.com") for i in range(5)]
        )
        r = await ac.get("/v1/users", params={"tenant_id": "acme"})
        assert r.json()["total"] == 5


# ---------------------------------------------------------------------------
# GET /v1/users/by-email/{email}
# ---------------------------------------------------------------------------


class TestGetByEmailEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/users/by-email/alice@example.com")
        assert r.status_code == 200

    async def test_returns_404_when_not_found(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.get_by_email = AsyncMock(side_effect=NotFoundError("nope"))
        r = await ac.get("/v1/users/by-email/ghost@x.com")
        assert r.status_code == 404

    async def test_calls_service_with_email(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        await ac.get("/v1/users/by-email/target@x.com")
        mock_svc.get_by_email.assert_awaited_once_with("target@x.com")


# ---------------------------------------------------------------------------
# GET /v1/users/{user_id}
# ---------------------------------------------------------------------------


class TestGetUserEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get(f"/v1/users/{uuid4()}")
        assert r.status_code == 200

    async def test_returns_404_when_not_found(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.get = AsyncMock(side_effect=NotFoundError("nope"))
        r = await ac.get(f"/v1/users/{uuid4()}")
        assert r.status_code == 404

    async def test_response_omits_password(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get(f"/v1/users/{uuid4()}")
        assert "hashed_password" not in r.json()


# ---------------------------------------------------------------------------
# PUT /v1/users/{user_id}
# ---------------------------------------------------------------------------


class TestUpdateUserEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.put(f"/v1/users/{uuid4()}", json={"role": "admin"})
        assert r.status_code == 200

    async def test_empty_body_is_valid(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.put(f"/v1/users/{uuid4()}", json={})
        assert r.status_code == 200

    async def test_returns_404_when_not_found(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.update = AsyncMock(side_effect=NotFoundError("nope"))
        r = await ac.put(f"/v1/users/{uuid4()}", json={"is_active": False})
        assert r.status_code == 404

    async def test_invalid_role_returns_422(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.put(f"/v1/users/{uuid4()}", json={"role": "superuser"})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /v1/users/{user_id}
# ---------------------------------------------------------------------------


class TestDeactivateUserEndpoint:
    async def test_returns_204(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.delete(f"/v1/users/{uuid4()}")
        assert r.status_code == 204

    async def test_returns_404_when_not_found(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.deactivate = AsyncMock(side_effect=NotFoundError("nope"))
        r = await ac.delete(f"/v1/users/{uuid4()}")
        assert r.status_code == 404

    async def test_calls_service_with_id(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        uid = uuid4()
        await ac.delete(f"/v1/users/{uid}")
        mock_svc.deactivate.assert_awaited_once_with(uid)


# ---------------------------------------------------------------------------
# POST /v1/users/{user_id}/change-password
# ---------------------------------------------------------------------------


class TestChangePasswordEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            f"/v1/users/{uuid4()}/change-password",
            json={"new_password": "newpassword123"},
        )
        assert r.status_code == 200

    async def test_short_password_returns_422(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            f"/v1/users/{uuid4()}/change-password", json={"new_password": "short"}
        )
        assert r.status_code == 422

    async def test_returns_404_when_not_found(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.change_password = AsyncMock(side_effect=NotFoundError("nope"))
        r = await ac.post(
            f"/v1/users/{uuid4()}/change-password",
            json={"new_password": "newpassword123"},
        )
        assert r.status_code == 404

    async def test_calls_service_with_new_password(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        uid = uuid4()
        await ac.post(
            f"/v1/users/{uid}/change-password",
            json={"new_password": "mynewpassword"},
        )
        mock_svc.change_password.assert_awaited_once_with(uid, "mynewpassword")
