"""Module 4 — Auth: HTTP route tests."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from common.auth.passwords import hash_password
from common.auth.tokens import create_access_token
from common.models.user import User
from services.auth.deps import get_auth_service
from services.auth.router import router
from services.auth.service import AuthService


def _make_user(password: str = "s3cr3t", role: str = "operator") -> User:
    user = User()
    user.id = uuid4()
    user.email = "alice@example.com"
    user.hashed_password = hash_password(password)
    user.tenant_id = "tenant-acme"
    user.role = role
    user.is_active = True
    return user


def _make_auth_service(user: User | None) -> AuthService:
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return AuthService(session)  # type: ignore[arg-type]


@pytest.fixture()
async def client_for(request: pytest.FixtureRequest) -> AsyncGenerator[AsyncClient, None]:
    user = getattr(request, "param", _make_user())
    app = FastAPI()
    app.include_router(router)

    async def override() -> AuthService:
        return _make_auth_service(user)

    app.dependency_overrides[get_auth_service] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture()
async def client(client_for: AsyncClient) -> AsyncClient:
    return client_for


class TestGetTokenEndpoint:
    async def test_valid_credentials_returns_200(self, client: AsyncClient) -> None:
        response = await client.post(
            "/v1/auth/token",
            json={"email": "alice@example.com", "password": "s3cr3t"},
        )
        assert response.status_code == 200

    async def test_response_has_access_token(self, client: AsyncClient) -> None:
        response = await client.post(
            "/v1/auth/token",
            json={"email": "alice@example.com", "password": "s3cr3t"},
        )
        body = response.json()
        assert "access_token" in body
        assert len(body["access_token"]) > 10

    async def test_response_token_type_is_bearer(self, client: AsyncClient) -> None:
        response = await client.post(
            "/v1/auth/token",
            json={"email": "alice@example.com", "password": "s3cr3t"},
        )
        assert response.json()["token_type"] == "bearer"

    async def test_response_has_expires_in(self, client: AsyncClient) -> None:
        response = await client.post(
            "/v1/auth/token",
            json={"email": "alice@example.com", "password": "s3cr3t"},
        )
        assert response.json()["expires_in"] > 0

    async def test_wrong_password_returns_401(self) -> None:
        # Service returns None (auth failed)
        app = FastAPI()
        app.include_router(router)

        async def override_none() -> AuthService:
            return _make_auth_service(None)

        app.dependency_overrides[get_auth_service] = override_none
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/v1/auth/token",
                json={"email": "alice@example.com", "password": "wrong"},
            )
        assert response.status_code == 401

    async def test_missing_email_returns_422(self, client: AsyncClient) -> None:
        response = await client.post(
            "/v1/auth/token", json={"password": "s3cr3t"}
        )
        assert response.status_code == 422

    async def test_missing_password_returns_422(self, client: AsyncClient) -> None:
        response = await client.post(
            "/v1/auth/token", json={"email": "alice@example.com"}
        )
        assert response.status_code == 422

    async def test_empty_password_returns_422(self, client: AsyncClient) -> None:
        response = await client.post(
            "/v1/auth/token",
            json={"email": "alice@example.com", "password": ""},
        )
        assert response.status_code == 422

    async def test_401_includes_www_authenticate_header(self) -> None:
        app = FastAPI()
        app.include_router(router)

        async def override_none() -> AuthService:
            return _make_auth_service(None)

        app.dependency_overrides[get_auth_service] = override_none
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/v1/auth/token",
                json={"email": "x@x.com", "password": "bad"},
            )
        assert "www-authenticate" in response.headers


class TestGetCurrentUserDependency:
    async def test_protected_route_with_valid_token_returns_200(self) -> None:
        user = _make_user()
        token = create_access_token(user.id, user.tenant_id, user.role)

        from fastapi import Depends

        from common.auth.deps import get_current_user
        from common.db import get_session

        app = FastAPI()

        @app.get("/protected")
        async def protected_route(
            current_user: User = Depends(get_current_user),
        ) -> dict[str, str]:
            return {"user_id": str(current_user.id)}

        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=result)

        async def mock_get_session() -> AsyncGenerator[MagicMock, None]:
            yield mock_session

        app.dependency_overrides[get_session] = mock_get_session
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.get(
                "/protected", headers={"Authorization": f"Bearer {token}"}
            )
        assert response.status_code == 200
        assert response.json()["user_id"] == str(user.id)

    async def test_protected_route_without_token_returns_403(self) -> None:
        app = FastAPI()

        @app.get("/protected")
        async def protected_route() -> dict[str, str]:
            return {"ok": "yes"}

        from fastapi import Depends

        from common.auth.deps import get_current_user

        @app.get("/secured")
        async def secured(user: User = Depends(get_current_user)) -> dict[str, str]:
            return {"user_id": str(user.id)}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.get("/secured")
        assert response.status_code == 403
