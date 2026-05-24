"""Module 5 — Sentinel: HTTP route tests."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from common.exceptions import NotFoundError
from common.models.policy import Policy
from common.models.sentinel import SentinelAlert
from services.sentinel.deps import get_sentinel_service
from services.sentinel.router import router
from services.sentinel.service import SentinelService


def _make_alert(*, is_resolved: bool = False) -> SentinelAlert:
    return SentinelAlert(
        id=uuid4(),
        tenant_id="tenant-acme",
        agent_id="agent-1",
        sentinel_type="tool_misuse",
        severity="high",
        message="Tool blocked",
        is_resolved=is_resolved,
    )


def _make_policy() -> Policy:
    return Policy(
        id=uuid4(),
        tenant_id="tenant-acme",
        name="Block misuse",
        sentinel_type="tool_misuse",
        severity="high",
        action="block_tool_call",
    )


def _make_service(alert: SentinelAlert | None = None, policy: Policy | None = None) -> MagicMock:
    svc = MagicMock(spec=SentinelService)
    svc.create_alert = AsyncMock(return_value=alert or _make_alert())
    svc.list_alerts = AsyncMock(return_value=[alert] if alert else [_make_alert()])
    svc.get_alert = AsyncMock(return_value=alert or _make_alert())
    svc.resolve_alert = AsyncMock(return_value=_make_alert(is_resolved=True))
    svc.create_policy = AsyncMock(return_value=policy or _make_policy())
    svc.list_policies = AsyncMock(return_value=[policy] if policy else [_make_policy()])
    svc.deactivate_policy = AsyncMock(return_value=_make_policy())
    return svc


@pytest.fixture()
async def client() -> AsyncGenerator[AsyncClient, None]:
    app = FastAPI()
    app.include_router(router)
    svc = _make_service()
    app.dependency_overrides[get_sentinel_service] = lambda: svc
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


_ALERT_PAYLOAD = {
    "tenant_id": "tenant-acme",
    "agent_id": "agent-1",
    "sentinel_type": "tool_misuse",
    "severity": "high",
    "message": "Tool blocked",
}

_POLICY_PAYLOAD = {
    "tenant_id": "tenant-acme",
    "name": "Block misuse",
    "sentinel_type": "tool_misuse",
    "severity": "high",
    "action": "block_tool_call",
}


class TestCreateAlertEndpoint:
    async def test_returns_201(self, client: AsyncClient) -> None:
        response = await client.post("/v1/sentinel/alerts", json=_ALERT_PAYLOAD)
        assert response.status_code == 201

    async def test_response_has_expected_fields(self, client: AsyncClient) -> None:
        response = await client.post("/v1/sentinel/alerts", json=_ALERT_PAYLOAD)
        body = response.json()
        assert "id" in body
        assert body["tenant_id"] == "tenant-acme"
        assert body["is_resolved"] is False

    async def test_missing_message_returns_422(self, client: AsyncClient) -> None:
        payload = {k: v for k, v in _ALERT_PAYLOAD.items() if k != "message"}
        response = await client.post("/v1/sentinel/alerts", json=payload)
        assert response.status_code == 422

    async def test_invalid_severity_returns_422(self, client: AsyncClient) -> None:
        response = await client.post(
            "/v1/sentinel/alerts", json={**_ALERT_PAYLOAD, "severity": "nuclear"}
        )
        assert response.status_code == 422


class TestListAlertsEndpoint:
    async def test_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/v1/sentinel/alerts?tenant_id=tenant-acme")
        assert response.status_code == 200

    async def test_response_has_alerts_and_total(self, client: AsyncClient) -> None:
        response = await client.get("/v1/sentinel/alerts?tenant_id=tenant-acme")
        body = response.json()
        assert "alerts" in body
        assert "total" in body
        assert body["total"] >= 0

    async def test_missing_tenant_id_returns_422(self, client: AsyncClient) -> None:
        response = await client.get("/v1/sentinel/alerts")
        assert response.status_code == 422


class TestGetAlertEndpoint:
    async def test_returns_200_when_found(self, client: AsyncClient) -> None:
        alert = _make_alert()
        app = FastAPI()
        app.include_router(router)
        svc = _make_service(alert=alert)
        app.dependency_overrides[get_sentinel_service] = lambda: svc
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.get(f"/v1/sentinel/alerts/{alert.id}")
        assert response.status_code == 200

    async def test_returns_404_when_not_found(self) -> None:
        app = FastAPI()
        app.include_router(router)
        svc = MagicMock(spec=SentinelService)
        svc.get_alert = AsyncMock(side_effect=NotFoundError("not found"))
        app.dependency_overrides[get_sentinel_service] = lambda: svc
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.get(f"/v1/sentinel/alerts/{uuid4()}")
        assert response.status_code == 404


class TestResolveAlertEndpoint:
    async def test_returns_200(self, client: AsyncClient) -> None:
        alert_id = uuid4()
        response = await client.post(
            f"/v1/sentinel/alerts/{alert_id}/resolve",
            json={"action": "warn"},
        )
        assert response.status_code == 200

    async def test_response_is_resolved(self, client: AsyncClient) -> None:
        response = await client.post(
            f"/v1/sentinel/alerts/{uuid4()}/resolve",
            json={"action": "warn"},
        )
        assert response.json()["is_resolved"] is True

    async def test_invalid_action_returns_422(self, client: AsyncClient) -> None:
        response = await client.post(
            f"/v1/sentinel/alerts/{uuid4()}/resolve",
            json={"action": "explode"},
        )
        assert response.status_code == 422

    async def test_returns_404_when_alert_not_found(self) -> None:
        app = FastAPI()
        app.include_router(router)
        svc = MagicMock(spec=SentinelService)
        svc.resolve_alert = AsyncMock(side_effect=NotFoundError("not found"))
        app.dependency_overrides[get_sentinel_service] = lambda: svc
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                f"/v1/sentinel/alerts/{uuid4()}/resolve",
                json={"action": "warn"},
            )
        assert response.status_code == 404


class TestCreatePolicyEndpoint:
    async def test_returns_201(self, client: AsyncClient) -> None:
        response = await client.post("/v1/sentinel/policies", json=_POLICY_PAYLOAD)
        assert response.status_code == 201

    async def test_response_has_expected_fields(self, client: AsyncClient) -> None:
        response = await client.post("/v1/sentinel/policies", json=_POLICY_PAYLOAD)
        body = response.json()
        assert "id" in body
        assert body["name"] == "Block misuse"
        assert body["is_active"] is True

    async def test_missing_name_returns_422(self, client: AsyncClient) -> None:
        payload = {k: v for k, v in _POLICY_PAYLOAD.items() if k != "name"}
        response = await client.post("/v1/sentinel/policies", json=payload)
        assert response.status_code == 422


class TestListPoliciesEndpoint:
    async def test_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/v1/sentinel/policies?tenant_id=tenant-acme")
        assert response.status_code == 200

    async def test_response_has_policies_and_total(self, client: AsyncClient) -> None:
        response = await client.get("/v1/sentinel/policies?tenant_id=tenant-acme")
        body = response.json()
        assert "policies" in body
        assert "total" in body


class TestDeactivatePolicyEndpoint:
    async def test_returns_204(self, client: AsyncClient) -> None:
        response = await client.delete(f"/v1/sentinel/policies/{uuid4()}")
        assert response.status_code == 204

    async def test_returns_404_when_not_found(self) -> None:
        app = FastAPI()
        app.include_router(router)
        svc = MagicMock(spec=SentinelService)
        svc.deactivate_policy = AsyncMock(side_effect=NotFoundError("not found"))
        app.dependency_overrides[get_sentinel_service] = lambda: svc
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.delete(f"/v1/sentinel/policies/{uuid4()}")
        assert response.status_code == 404
