"""Module 6 — API exception handler tests."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from common.api.exceptions import add_exception_handlers
from common.exceptions import (
    AuthenticationError,
    AuthorizationError,
    DoxException,
    NotFoundError,
    QuotaExceededError,
    RateLimitError,
    ValidationError,
)


@pytest.fixture()
async def client() -> AsyncClient:
    app = FastAPI()
    add_exception_handlers(app)

    @app.get("/not-found")
    async def _nf() -> None:
        raise NotFoundError("thing not found")

    @app.get("/auth-error")
    async def _ae() -> None:
        raise AuthenticationError("bad credentials")

    @app.get("/authz-error")
    async def _authz() -> None:
        raise AuthorizationError("no permission")

    @app.get("/validation-error")
    async def _ve() -> None:
        raise ValidationError("bad input")

    @app.get("/rate-limit")
    async def _rl() -> None:
        raise RateLimitError("too many requests", retry_after=30)

    @app.get("/quota-exceeded")
    async def _qe() -> None:
        raise QuotaExceededError("monthly limit reached")

    @app.get("/generic-dox")
    async def _gd() -> None:
        raise DoxException("something broke", code="broken")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac  # type: ignore[misc]


class TestNotFoundHandler:
    async def test_returns_404(self, client: AsyncClient) -> None:
        r = await client.get("/not-found")
        assert r.status_code == 404

    async def test_body_has_error_and_detail(self, client: AsyncClient) -> None:
        r = await client.get("/not-found")
        body = r.json()
        assert body["error"] == "not_found"
        assert "thing not found" in body["detail"]


class TestAuthenticationHandler:
    async def test_returns_401(self, client: AsyncClient) -> None:
        r = await client.get("/auth-error")
        assert r.status_code == 401

    async def test_has_www_authenticate_header(self, client: AsyncClient) -> None:
        r = await client.get("/auth-error")
        assert r.headers.get("www-authenticate") == "Bearer"

    async def test_body_has_authentication_error_code(self, client: AsyncClient) -> None:
        r = await client.get("/auth-error")
        assert r.json()["error"] == "authentication_error"


class TestAuthorizationHandler:
    async def test_returns_403(self, client: AsyncClient) -> None:
        r = await client.get("/authz-error")
        assert r.status_code == 403

    async def test_body_has_authorization_error_code(self, client: AsyncClient) -> None:
        r = await client.get("/authz-error")
        assert r.json()["error"] == "authorization_error"


class TestValidationHandler:
    async def test_returns_422(self, client: AsyncClient) -> None:
        r = await client.get("/validation-error")
        assert r.status_code == 422

    async def test_body_has_validation_error_code(self, client: AsyncClient) -> None:
        r = await client.get("/validation-error")
        assert r.json()["error"] == "validation_error"


class TestRateLimitHandler:
    async def test_returns_429(self, client: AsyncClient) -> None:
        r = await client.get("/rate-limit")
        assert r.status_code == 429

    async def test_has_retry_after_header(self, client: AsyncClient) -> None:
        r = await client.get("/rate-limit")
        assert r.headers.get("retry-after") == "30"

    async def test_body_has_rate_limit_code(self, client: AsyncClient) -> None:
        r = await client.get("/rate-limit")
        assert r.json()["error"] == "rate_limit_exceeded"


class TestQuotaExceededHandler:
    async def test_returns_429(self, client: AsyncClient) -> None:
        r = await client.get("/quota-exceeded")
        assert r.status_code == 429

    async def test_body_has_quota_exceeded_code(self, client: AsyncClient) -> None:
        r = await client.get("/quota-exceeded")
        assert r.json()["error"] == "quota_exceeded"


class TestGenericDoxHandler:
    async def test_returns_400(self, client: AsyncClient) -> None:
        r = await client.get("/generic-dox")
        assert r.status_code == 400

    async def test_body_has_custom_code(self, client: AsyncClient) -> None:
        r = await client.get("/generic-dox")
        assert r.json()["error"] == "broken"
