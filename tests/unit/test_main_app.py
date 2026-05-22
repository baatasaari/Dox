"""Module 15 — Application Assembly: main app structure and behaviour tests."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from common.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    QuotaExceededError,
    RateLimitError,
    ValidationError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXPECTED_PREFIXES = [
    "/v1/audit-log",
    "/v1/auth",
    "/v1/compliance",
    "/v1/drift",
    "/v1/events",
    "/v1/notify",
    "/v1/policies",
    "/v1/audit",
    "/v1/quota",
    "/v1/agents",
    "/v1/sentinel",
    "/v1/tenants",
    "/v1/users",
]


def _route_prefixes(app: FastAPI) -> set[str]:
    prefixes: set[str] = set()
    for route in app.routes:
        path: str = getattr(route, "path", "")
        for prefix in _EXPECTED_PREFIXES:
            if path.startswith(prefix):
                prefixes.add(prefix)
                break
    return prefixes


@pytest.fixture()
def app() -> FastAPI:
    return create_app()


@pytest.fixture()
async def client(app: FastAPI) -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac  # type: ignore[misc]


@pytest.fixture()
def app_with_error_routes() -> FastAPI:
    """App with extra routes that raise specific DoxException subclasses."""
    a = create_app()

    @a.get("/test/not-found")
    async def _not_found() -> None:
        raise NotFoundError("test resource missing")

    @a.get("/test/auth-error")
    async def _auth() -> None:
        raise AuthenticationError("bad token")

    @a.get("/test/authz-error")
    async def _authz() -> None:
        raise AuthorizationError("forbidden")

    @a.get("/test/validation-error")
    async def _validation() -> None:
        raise ValidationError("bad input")

    @a.get("/test/quota-error")
    async def _quota() -> None:
        raise QuotaExceededError("over limit")

    @a.get("/test/rate-limit")
    async def _rate() -> None:
        raise RateLimitError("slow down", retry_after=5)

    @a.get("/test/generic-dox")
    async def _generic() -> None:
        raise ConflictError("conflict")

    return a


# ---------------------------------------------------------------------------
# App creation
# ---------------------------------------------------------------------------


class TestCreateApp:
    def test_returns_fastapi_instance(self, app: FastAPI) -> None:
        assert isinstance(app, FastAPI)

    def test_title_contains_dox(self, app: FastAPI) -> None:
        assert "Dox" in app.title

    def test_version_is_set(self, app: FastAPI) -> None:
        assert app.version

    def test_description_is_set(self, app: FastAPI) -> None:
        assert app.description

    def test_separate_calls_return_distinct_instances(self) -> None:
        a1 = create_app()
        a2 = create_app()
        assert a1 is not a2


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------


class TestHealthEndpoints:
    async def test_healthz_returns_200(self, client: AsyncClient) -> None:
        r = await client.get("/healthz")
        assert r.status_code == 200

    async def test_healthz_body(self, client: AsyncClient) -> None:
        r = await client.get("/healthz")
        assert r.json() == {"status": "ok"}

    async def test_readyz_returns_200(self, client: AsyncClient) -> None:
        r = await client.get("/readyz")
        assert r.status_code == 200

    async def test_readyz_body(self, client: AsyncClient) -> None:
        r = await client.get("/readyz")
        assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# OpenAPI
# ---------------------------------------------------------------------------


class TestOpenAPI:
    async def test_openapi_json_accessible(self, client: AsyncClient) -> None:
        r = await client.get("/openapi.json")
        assert r.status_code == 200

    async def test_openapi_has_info(self, client: AsyncClient) -> None:
        schema = (await client.get("/openapi.json")).json()
        assert "info" in schema
        assert "Dox" in schema["info"]["title"]

    async def test_openapi_has_paths(self, client: AsyncClient) -> None:
        schema = (await client.get("/openapi.json")).json()
        assert len(schema.get("paths", {})) > 0

    async def test_docs_accessible(self, client: AsyncClient) -> None:
        r = await client.get("/docs")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Router mounting
# ---------------------------------------------------------------------------


class TestRouterMounting:
    @pytest.mark.parametrize("prefix", _EXPECTED_PREFIXES)
    def test_prefix_mounted(self, app: FastAPI, prefix: str) -> None:
        assert prefix in _route_prefixes(app), f"No route found with prefix {prefix!r}"

    def test_all_prefixes_mounted(self, app: FastAPI) -> None:
        mounted = _route_prefixes(app)
        missing = set(_EXPECTED_PREFIXES) - mounted
        assert not missing, f"Missing route prefixes: {missing}"

    def test_health_routes_present(self, app: FastAPI) -> None:
        paths = {getattr(r, "path", "") for r in app.routes}
        assert "/healthz" in paths
        assert "/readyz" in paths


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


class TestExceptionHandlers:
    async def test_not_found_maps_to_404(self, app_with_error_routes: FastAPI) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_error_routes), base_url="http://test"
        ) as ac:
            r = await ac.get("/test/not-found")
        assert r.status_code == 404
        assert r.json()["error"] == "not_found"

    async def test_authentication_error_maps_to_401(
        self, app_with_error_routes: FastAPI
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_error_routes), base_url="http://test"
        ) as ac:
            r = await ac.get("/test/auth-error")
        assert r.status_code == 401
        assert "WWW-Authenticate" in r.headers

    async def test_authorization_error_maps_to_403(
        self, app_with_error_routes: FastAPI
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_error_routes), base_url="http://test"
        ) as ac:
            r = await ac.get("/test/authz-error")
        assert r.status_code == 403

    async def test_validation_error_maps_to_422(self, app_with_error_routes: FastAPI) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_error_routes), base_url="http://test"
        ) as ac:
            r = await ac.get("/test/validation-error")
        assert r.status_code == 422

    async def test_quota_exceeded_maps_to_429(self, app_with_error_routes: FastAPI) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_error_routes), base_url="http://test"
        ) as ac:
            r = await ac.get("/test/quota-error")
        assert r.status_code == 429
        assert r.json()["error"] == "quota_exceeded"

    async def test_rate_limit_maps_to_429_with_retry_after(
        self, app_with_error_routes: FastAPI
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_error_routes), base_url="http://test"
        ) as ac:
            r = await ac.get("/test/rate-limit")
        assert r.status_code == 429
        assert "Retry-After" in r.headers

    async def test_generic_dox_maps_to_400(self, app_with_error_routes: FastAPI) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_error_routes), base_url="http://test"
        ) as ac:
            r = await ac.get("/test/generic-dox")
        assert r.status_code == 400

    async def test_error_body_has_error_and_detail_keys(
        self, app_with_error_routes: FastAPI
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_error_routes), base_url="http://test"
        ) as ac:
            r = await ac.get("/test/not-found")
        body = r.json()
        assert "error" in body
        assert "detail" in body


# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------


class TestCORSMiddleware:
    async def test_cors_header_present_on_preflight(self, client: AsyncClient) -> None:
        r = await client.options(
            "/healthz",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" in r.headers

    async def test_cors_header_present_on_regular_request(self, client: AsyncClient) -> None:
        r = await client.get("/healthz", headers={"Origin": "https://example.com"})
        assert "access-control-allow-origin" in r.headers

    async def test_custom_cors_origins_respected(self) -> None:
        restricted = create_app(cors_origins=["https://trusted.example.com"])
        async with AsyncClient(
            transport=ASGITransport(app=restricted), base_url="http://test"
        ) as ac:
            r = await ac.get("/healthz", headers={"Origin": "https://trusted.example.com"})
        assert r.headers.get("access-control-allow-origin") == "https://trusted.example.com"
