"""Module 15 — Application Assembly: cross-service integration through the full app."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from common.exceptions import ConflictError, NotFoundError
from common.models.tenant import Tenant
from common.models.user import User
from common.schemas.compliance import (
    AlertSummary,
    ComplianceReport,
    EventSummary,
    PolicySummary,
    QuotaSummary,
)
from common.schemas.enums import UserRole
from services.compliance.deps import get_compliance_service
from services.compliance.service import ComplianceService
from services.tenant.deps import get_tenant_service
from services.tenant.service import TenantService
from services.users.deps import get_user_service
from services.users.service import UserService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _make_user(email: str = "alice@example.com", tenant_id: str = "acme") -> User:
    return User(
        id=uuid4(),
        email=email,
        hashed_password="hashed",
        tenant_id=tenant_id,
        role=UserRole.viewer,
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )


def _make_tenant(slug: str = "acme", name: str = "Acme Corp") -> Tenant:
    return Tenant(
        id=uuid4(),
        slug=slug,
        name=name,
        subscription_tier="starter",
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )


def _make_compliance_report(tenant_id: str = "acme") -> ComplianceReport:
    return ComplianceReport(
        tenant_id=tenant_id,
        generated_at=_now(),
        lookback_hours=24,
        events=EventSummary(total_count=10, by_type={"tool_call": 10}, lookback_hours=24),
        alerts=AlertSummary(
            total_count=2,
            unresolved_count=1,
            by_severity={"high": 1, "medium": 1},
            by_type={"policy_violation": 2},
        ),
        quota=QuotaSummary(
            subscription_tier="starter",
            daily_remaining=900,
            monthly_remaining=19000,
            is_over_daily_limit=False,
            is_over_monthly_limit=False,
        ),
        policies=PolicySummary(active_count=3),
    )


def _mock_user_service(user: User | None = None) -> MagicMock:
    u = user or _make_user()
    svc = MagicMock(spec=UserService)
    svc.create = AsyncMock(return_value=u)
    svc.get = AsyncMock(return_value=u)
    svc.get_by_email = AsyncMock(return_value=u)
    svc.list_for_tenant = AsyncMock(return_value=[u])
    svc.update = AsyncMock(return_value=u)
    svc.deactivate = AsyncMock(return_value=None)
    svc.change_password = AsyncMock(return_value=u)
    return svc


def _mock_tenant_service(tenant: Tenant | None = None) -> MagicMock:
    t = tenant or _make_tenant()
    svc = MagicMock(spec=TenantService)
    svc.create = AsyncMock(return_value=t)
    svc.get = AsyncMock(return_value=t)
    svc.get_by_slug = AsyncMock(return_value=t)
    svc.list_tenants = AsyncMock(return_value=[t])
    svc.update = AsyncMock(return_value=t)
    svc.deactivate = AsyncMock(return_value=None)
    svc.activate = AsyncMock(return_value=t)
    return svc


def _mock_compliance_service(report: ComplianceReport | None = None) -> MagicMock:
    r = report or _make_compliance_report()
    svc = MagicMock(spec=ComplianceService)
    svc.generate_report = AsyncMock(return_value=r)
    return svc


@pytest.fixture()
async def client() -> AsyncGenerator[AsyncClient, None]:
    app = create_app()
    user_svc = _mock_user_service()
    tenant_svc = _mock_tenant_service()
    compliance_svc = _mock_compliance_service()

    app.dependency_overrides[get_user_service] = lambda: user_svc
    app.dependency_overrides[get_tenant_service] = lambda: tenant_svc
    app.dependency_overrides[get_compliance_service] = lambda: compliance_svc

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# User flow through full app
# ---------------------------------------------------------------------------


class TestUserFlowThroughApp:
    async def test_create_user_returns_201(self, client: AsyncClient) -> None:
        r = await client.post(
            "/v1/users",
            json={"email": "new@example.com", "password": "secret123", "tenant_id": "acme"},
        )
        assert r.status_code == 201

    async def test_created_user_omits_password(self, client: AsyncClient) -> None:
        r = await client.post(
            "/v1/users",
            json={"email": "new@example.com", "password": "secret123", "tenant_id": "acme"},
        )
        assert "hashed_password" not in r.json()

    async def test_list_users_returns_200(self, client: AsyncClient) -> None:
        r = await client.get("/v1/users", params={"tenant_id": "acme"})
        assert r.status_code == 200
        assert "users" in r.json()
        assert "total" in r.json()

    async def test_conflict_on_duplicate_email_returns_409(self, client: AsyncClient) -> None:
        app = create_app()
        conflict_svc = _mock_user_service()
        conflict_svc.create = AsyncMock(side_effect=ConflictError("dup"))
        app.dependency_overrides[get_user_service] = lambda: conflict_svc

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post(
                "/v1/users",
                json={"email": "dup@example.com", "password": "secret123", "tenant_id": "t"},
            )
        assert r.status_code == 409

    async def test_get_user_by_email_returns_200(self, client: AsyncClient) -> None:
        r = await client.get("/v1/users/by-email/alice@example.com")
        assert r.status_code == 200

    async def test_deactivate_user_returns_204(self, client: AsyncClient) -> None:
        r = await client.delete(f"/v1/users/{uuid4()}")
        assert r.status_code == 204

    async def test_change_password_returns_200(self, client: AsyncClient) -> None:
        r = await client.post(
            f"/v1/users/{uuid4()}/change-password",
            json={"new_password": "newpassword123"},
        )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Tenant flow through full app
# ---------------------------------------------------------------------------


class TestTenantFlowThroughApp:
    async def test_create_tenant_returns_201(self, client: AsyncClient) -> None:
        r = await client.post(
            "/v1/tenants", json={"slug": "acme", "name": "Acme Corp"}
        )
        assert r.status_code == 201

    async def test_list_tenants_returns_200(self, client: AsyncClient) -> None:
        r = await client.get("/v1/tenants")
        assert r.status_code == 200
        body = r.json()
        assert "tenants" in body
        assert "total" in body

    async def test_get_tenant_by_slug_returns_200(self, client: AsyncClient) -> None:
        r = await client.get("/v1/tenants/by-slug/acme")
        assert r.status_code == 200

    async def test_deactivate_tenant_returns_204(self, client: AsyncClient) -> None:
        r = await client.delete(f"/v1/tenants/{uuid4()}")
        assert r.status_code == 204

    async def test_tenant_not_found_returns_404(self, client: AsyncClient) -> None:
        app = create_app()
        missing_svc = _mock_tenant_service()
        missing_svc.get = AsyncMock(side_effect=NotFoundError("nope"))
        app.dependency_overrides[get_tenant_service] = lambda: missing_svc

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.get(f"/v1/tenants/{uuid4()}")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Cross-service flow through full app
# ---------------------------------------------------------------------------


class TestCrossServiceFlowThroughApp:
    async def test_compliance_report_returns_200(self, client: AsyncClient) -> None:
        r = await client.get("/v1/compliance/acme")
        assert r.status_code == 200

    async def test_compliance_report_has_all_sections(self, client: AsyncClient) -> None:
        r = await client.get("/v1/compliance/acme")
        body = r.json()
        assert "events" in body
        assert "alerts" in body
        assert "quota" in body
        assert "policies" in body

    async def test_tenant_then_user_then_compliance(self, client: AsyncClient) -> None:
        t = await client.post("/v1/tenants", json={"slug": "corp", "name": "Corp"})
        assert t.status_code == 201

        u = await client.post(
            "/v1/users",
            json={"email": "admin@corp.com", "password": "secret123", "tenant_id": "corp"},
        )
        assert u.status_code == 201
        assert "hashed_password" not in u.json()

        c = await client.get("/v1/compliance/corp")
        assert c.status_code == 200
        assert c.json()["events"]["total_count"] >= 0

    async def test_health_not_affected_by_service_errors(self) -> None:
        app = create_app()
        broken_svc = _mock_user_service()
        broken_svc.list_for_tenant = AsyncMock(side_effect=RuntimeError("db down"))
        app.dependency_overrides[get_user_service] = lambda: broken_svc

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            health = await ac.get("/healthz")
        assert health.status_code == 200

    async def test_openapi_lists_all_service_tags(self, client: AsyncClient) -> None:
        schema = (await client.get("/openapi.json")).json()
        operation_tags: set[str] = set()
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                if isinstance(operation, dict):
                    operation_tags.update(operation.get("tags", []))
        expected_tags = {"users", "tenants", "registry", "compliance", "notify"}
        assert expected_tags.issubset(operation_tags)
