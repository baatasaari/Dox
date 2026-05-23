"""Module 19 — RBAC Enforcement: dependency and role-gate tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from common.auth.dependencies import get_current_user, require_role
from common.auth.tokens import TokenPayload
from common.exceptions import AuthenticationError, AuthorizationError
from common.schemas.enums import UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _payload(role: str = "admin", tenant_id: str = "acme") -> TokenPayload:
    return TokenPayload(
        sub=str(uuid4()),
        tenant_id=tenant_id,
        role=role,
        exp=9_999_999_999,
    )


def _app_with_role_gate(*roles: UserRole) -> FastAPI:
    """Build a minimal FastAPI app with a single protected endpoint."""
    app = FastAPI()
    app.add_exception_handler(
        AuthenticationError,
        lambda req, exc: __import__("fastapi.responses", fromlist=["JSONResponse"]).JSONResponse(
            status_code=401, content={"detail": exc.detail}
        ),
    )
    app.add_exception_handler(
        AuthorizationError,
        lambda req, exc: __import__("fastapi.responses", fromlist=["JSONResponse"]).JSONResponse(
            status_code=403, content={"detail": exc.detail}
        ),
    )

    @app.get("/protected", dependencies=[require_role(*roles)])
    async def _protected() -> dict[str, str]:
        return {"ok": "true"}

    return app


def _role_client(role: str) -> AsyncClient:
    """Return an AsyncClient with get_current_user overridden — no service mocks."""
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _payload(role)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# get_current_user dependency
# ---------------------------------------------------------------------------


class TestGetCurrentUser:
    async def test_valid_token_returns_payload(self) -> None:
        from common.auth.tokens import create_access_token

        token = create_access_token(uuid4(), "acme", "admin")
        app = FastAPI()

        @app.get("/me")
        async def _me(payload: TokenPayload = __import__(
            "fastapi", fromlist=["Depends"]
        ).Depends(get_current_user)) -> dict[str, str]:
            return {"role": payload.role}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    async def test_missing_token_raises_authentication_error(self) -> None:
        app = _app_with_role_gate(UserRole.admin)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/protected")
        assert r.status_code == 401

    async def test_invalid_token_raises_authentication_error(self) -> None:
        app = _app_with_role_gate(UserRole.admin)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/protected", headers={"Authorization": "Bearer not.a.jwt"})
        assert r.status_code == 401

    async def test_dependency_override_bypasses_jwt(self) -> None:
        app = FastAPI()

        @app.get("/me")
        async def _me(payload: TokenPayload = __import__(
            "fastapi", fromlist=["Depends"]
        ).Depends(get_current_user)) -> dict[str, str]:
            return {"role": payload.role}

        app.dependency_overrides[get_current_user] = lambda: _payload("viewer")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/me")
        assert r.status_code == 200
        assert r.json()["role"] == "viewer"


# ---------------------------------------------------------------------------
# require_role — allowed access
# ---------------------------------------------------------------------------


class TestRequireRoleAllowed:
    async def test_admin_can_access_admin_only_route(self) -> None:
        app = _app_with_role_gate(UserRole.admin)
        app.dependency_overrides[get_current_user] = lambda: _payload("admin")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/protected")
        assert r.status_code == 200

    async def test_operator_can_access_operator_route(self) -> None:
        app = _app_with_role_gate(UserRole.operator, UserRole.admin)
        app.dependency_overrides[get_current_user] = lambda: _payload("operator")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/protected")
        assert r.status_code == 200

    async def test_admin_can_access_operator_route(self) -> None:
        app = _app_with_role_gate(UserRole.operator, UserRole.admin)
        app.dependency_overrides[get_current_user] = lambda: _payload("admin")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/protected")
        assert r.status_code == 200

    async def test_viewer_can_access_any_authenticated_route(self) -> None:
        app = _app_with_role_gate(
            UserRole.viewer, UserRole.operator, UserRole.admin, UserRole.agent
        )
        app.dependency_overrides[get_current_user] = lambda: _payload("viewer")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/protected")
        assert r.status_code == 200

    async def test_agent_can_access_agent_allowed_route(self) -> None:
        app = _app_with_role_gate(UserRole.agent, UserRole.operator, UserRole.admin)
        app.dependency_overrides[get_current_user] = lambda: _payload("agent")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/protected")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# require_role — denied access
# ---------------------------------------------------------------------------


class TestRequireRoleDenied:
    async def test_viewer_cannot_access_admin_only_route(self) -> None:
        app = _app_with_role_gate(UserRole.admin)
        app.dependency_overrides[get_current_user] = lambda: _payload("viewer")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/protected")
        assert r.status_code == 403

    async def test_agent_cannot_access_viewer_route(self) -> None:
        app = _app_with_role_gate(UserRole.viewer, UserRole.operator, UserRole.admin)
        app.dependency_overrides[get_current_user] = lambda: _payload("agent")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/protected")
        assert r.status_code == 403

    async def test_operator_cannot_access_admin_only_route(self) -> None:
        app = _app_with_role_gate(UserRole.admin)
        app.dependency_overrides[get_current_user] = lambda: _payload("operator")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/protected")
        assert r.status_code == 403

    async def test_viewer_cannot_access_operator_route(self) -> None:
        app = _app_with_role_gate(UserRole.operator, UserRole.admin)
        app.dependency_overrides[get_current_user] = lambda: _payload("viewer")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/protected")
        assert r.status_code == 403

    async def test_unauthenticated_cannot_access_any_route(self) -> None:
        app = _app_with_role_gate(UserRole.viewer, UserRole.operator, UserRole.admin)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/protected")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Role access matrix via full app
# ---------------------------------------------------------------------------


class TestFullAppRoleMatrix:
    # -- Denial tests: auth layer rejects before service layer is reached --

    async def test_viewer_cannot_reach_tenants_endpoint(self) -> None:
        async with _role_client("viewer") as ac:
            r = await ac.get("/v1/tenants")
        assert r.status_code == 403

    async def test_operator_cannot_reach_tenants_endpoint(self) -> None:
        async with _role_client("operator") as ac:
            r = await ac.get("/v1/tenants")
        assert r.status_code == 403

    async def test_viewer_cannot_reach_users_endpoint(self) -> None:
        async with _role_client("viewer") as ac:
            r = await ac.get("/v1/users", params={"tenant_id": "acme"})
        assert r.status_code == 403

    async def test_agent_cannot_reach_sentinel_alerts(self) -> None:
        async with _role_client("agent") as ac:
            r = await ac.get("/v1/sentinel/alerts", params={"tenant_id": "t"})
        assert r.status_code == 403

    async def test_viewer_cannot_reach_ingestion_endpoint(self) -> None:
        # require_role runs before body parsing — viewer blocked at auth, not body validation
        async with _role_client("viewer") as ac:
            r = await ac.post("/v1/events", json={})
        assert r.status_code == 403

    # -- Access tests: auth passes, service mocked to prevent DB calls --

    async def test_admin_can_reach_tenants_endpoint(self) -> None:
        from app.main import create_app
        from services.tenant.deps import get_tenant_service
        from services.tenant.service import TenantService

        app = create_app()
        svc = MagicMock(spec=TenantService)
        svc.list_tenants = AsyncMock(return_value=[])
        app.dependency_overrides[get_current_user] = lambda: _payload("admin")
        app.dependency_overrides[get_tenant_service] = lambda: svc
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.get("/v1/tenants")
        assert r.status_code not in (401, 403)

    async def test_admin_can_reach_users_endpoint(self) -> None:
        from app.main import create_app
        from services.users.deps import get_user_service
        from services.users.service import UserService

        app = create_app()
        svc = MagicMock(spec=UserService)
        svc.list_for_tenant = AsyncMock(return_value=[])
        app.dependency_overrides[get_current_user] = lambda: _payload("admin")
        app.dependency_overrides[get_user_service] = lambda: svc
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.get("/v1/users", params={"tenant_id": "acme"})
        assert r.status_code not in (401, 403)

    async def test_viewer_can_reach_sentinel_alerts(self) -> None:
        from app.main import create_app
        from services.sentinel.deps import get_sentinel_service
        from services.sentinel.service import SentinelService

        app = create_app()
        svc = MagicMock(spec=SentinelService)
        svc.list_alerts = AsyncMock(return_value=[])
        app.dependency_overrides[get_current_user] = lambda: _payload("viewer")
        app.dependency_overrides[get_sentinel_service] = lambda: svc
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.get("/v1/sentinel/alerts", params={"tenant_id": "t"})
        assert r.status_code not in (401, 403)

    async def test_agent_can_reach_ingestion_endpoint(self) -> None:
        from app.main import create_app
        from services.ingestion.deps import get_ingestion_service
        from services.ingestion.service import IngestionService

        app = create_app()
        svc = MagicMock(spec=IngestionService)
        app.dependency_overrides[get_current_user] = lambda: _payload("agent")
        app.dependency_overrides[get_ingestion_service] = lambda: svc
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post("/v1/events", json={})
        assert r.status_code not in (401, 403)

    # -- Public endpoints --

    async def test_no_token_returns_401_on_protected_route(self) -> None:
        from app.main import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/sentinel/alerts", params={"tenant_id": "t"})
        assert r.status_code == 401

    async def test_auth_token_endpoint_is_public(self) -> None:
        from app.main import create_app
        from services.auth.deps import get_auth_service
        from services.auth.service import AuthService

        app = create_app()
        svc = MagicMock(spec=AuthService)
        svc.authenticate = AsyncMock(return_value=None)
        app.dependency_overrides[get_auth_service] = lambda: svc
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/auth/token", json={"email": "x@x.com", "password": "wrong"}
            )
        # 401 (bad creds) is fine — NOT 403 (no auth requirement on this route)
        assert r.status_code == 401

    async def test_health_endpoint_is_public(self) -> None:
        from app.main import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/healthz")
        assert r.status_code == 200
