"""Module 11 — Agent Registry: HTTP route tests."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from common.exceptions import ConflictError, NotFoundError
from common.models.agent import AgentProfile
from services.registry.deps import get_registry_service
from services.registry.router import router
from services.registry.service import AgentRegistryService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(
    *,
    tenant_id: str = "tenant-acme",
    agent_id: str = "agent-1",
    name: str = "Bot",
    version: str = "1.0",
) -> AgentProfile:
    now = datetime.now(UTC)
    return AgentProfile(
        id=uuid4(),
        tenant_id=tenant_id,
        agent_id=agent_id,
        name=name,
        version=version,
        created_at=now,
        updated_at=now,
    )


def _make_mock_service(profile: AgentProfile | None = None) -> MagicMock:
    svc = MagicMock(spec=AgentRegistryService)
    p = profile or _make_profile()
    svc.create = AsyncMock(return_value=p)
    svc.get = AsyncMock(return_value=p)
    svc.get_by_agent_id = AsyncMock(return_value=p)
    svc.update = AsyncMock(return_value=p)
    svc.delete = AsyncMock(return_value=None)
    svc.list_for_tenant = AsyncMock(return_value=[p])
    svc.heartbeat = AsyncMock(return_value=p)
    return svc


@pytest.fixture()
async def client() -> AsyncGenerator[tuple[AsyncClient, MagicMock], None]:
    app = FastAPI()
    app.include_router(router)
    mock_svc = _make_mock_service()

    async def override() -> AgentRegistryService:
        return mock_svc  # type: ignore[return-value]

    app.dependency_overrides[get_registry_service] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_svc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# POST /v1/agents
# ---------------------------------------------------------------------------


class TestRegisterAgentEndpoint:
    async def test_returns_201(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/agents",
            json={"tenant_id": "acme", "agent_id": "bot", "name": "Bot", "version": "1.0"},
        )
        assert r.status_code == 201

    async def test_response_has_agent_fields(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/agents",
            json={"tenant_id": "acme", "agent_id": "bot", "name": "Bot", "version": "1.0"},
        )
        body = r.json()
        assert "id" in body
        assert "agent_id" in body
        assert "tenant_id" in body
        assert "name" in body
        assert "version" in body

    async def test_returns_409_on_conflict(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        mock_svc.create = AsyncMock(side_effect=ConflictError("duplicate"))
        r = await ac.post(
            "/v1/agents",
            json={"tenant_id": "acme", "agent_id": "bot", "name": "Bot", "version": "1.0"},
        )
        assert r.status_code == 409

    async def test_missing_name_returns_422(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/agents", json={"tenant_id": "acme", "agent_id": "bot"}
        )
        assert r.status_code == 422

    async def test_calls_service_with_payload(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        await ac.post(
            "/v1/agents",
            json={"tenant_id": "acme", "agent_id": "bot", "name": "Bot", "version": "2.0"},
        )
        mock_svc.create.assert_awaited_once()
        req = mock_svc.create.call_args[0][0]
        assert req.tenant_id == "acme"
        assert req.agent_id == "bot"
        assert req.version == "2.0"


# ---------------------------------------------------------------------------
# GET /v1/agents
# ---------------------------------------------------------------------------


class TestListAgentsEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/agents", params={"tenant_id": "acme"})
        assert r.status_code == 200

    async def test_response_has_list_shape(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/agents", params={"tenant_id": "acme"})
        body = r.json()
        assert "agents" in body
        assert "total" in body

    async def test_total_reflects_count(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        profiles = [_make_profile(agent_id=f"a-{i}") for i in range(3)]
        mock_svc.list_for_tenant = AsyncMock(return_value=profiles)
        r = await ac.get("/v1/agents", params={"tenant_id": "acme"})
        assert r.json()["total"] == 3

    async def test_missing_tenant_id_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get("/v1/agents")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /v1/agents/{profile_id}
# ---------------------------------------------------------------------------


class TestGetAgentEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get(f"/v1/agents/{uuid4()}")
        assert r.status_code == 200

    async def test_returns_404_when_not_found(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.get = AsyncMock(side_effect=NotFoundError("nope"))
        r = await ac.get(f"/v1/agents/{uuid4()}")
        assert r.status_code == 404

    async def test_calls_service_with_correct_id(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        pid = uuid4()
        await ac.get(f"/v1/agents/{pid}")
        mock_svc.get.assert_awaited_once_with(pid)


# ---------------------------------------------------------------------------
# PUT /v1/agents/{profile_id}
# ---------------------------------------------------------------------------


class TestUpdateAgentEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.put(f"/v1/agents/{uuid4()}", json={"name": "new name"})
        assert r.status_code == 200

    async def test_empty_body_is_valid(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.put(f"/v1/agents/{uuid4()}", json={})
        assert r.status_code == 200

    async def test_returns_404_when_not_found(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.update = AsyncMock(side_effect=NotFoundError("nope"))
        r = await ac.put(f"/v1/agents/{uuid4()}", json={"name": "x"})
        assert r.status_code == 404

    async def test_calls_service_with_update(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        pid = uuid4()
        await ac.put(f"/v1/agents/{pid}", json={"is_active": False})
        mock_svc.update.assert_awaited_once()
        call_args = mock_svc.update.call_args
        assert call_args[0][0] == pid
        assert call_args[0][1].is_active is False


# ---------------------------------------------------------------------------
# DELETE /v1/agents/{profile_id}
# ---------------------------------------------------------------------------


class TestDeactivateAgentEndpoint:
    async def test_returns_204(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.delete(f"/v1/agents/{uuid4()}")
        assert r.status_code == 204

    async def test_returns_404_when_not_found(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.delete = AsyncMock(side_effect=NotFoundError("nope"))
        r = await ac.delete(f"/v1/agents/{uuid4()}")
        assert r.status_code == 404

    async def test_calls_service_with_id(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        pid = uuid4()
        await ac.delete(f"/v1/agents/{pid}")
        mock_svc.delete.assert_awaited_once_with(pid)


# ---------------------------------------------------------------------------
# POST /v1/agents/{tenant_id}/{agent_id}/heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeatEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        profile = _make_profile()
        profile.last_seen_at = datetime.now(UTC)
        mock_svc.heartbeat = AsyncMock(return_value=profile)
        r = await ac.post("/v1/agents/tenant-acme/agent-1/heartbeat")
        assert r.status_code == 200

    async def test_response_has_heartbeat_fields(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        profile = _make_profile()
        profile.last_seen_at = datetime.now(UTC)
        mock_svc.heartbeat = AsyncMock(return_value=profile)
        r = await ac.post("/v1/agents/tenant-acme/agent-1/heartbeat")
        body = r.json()
        assert "agent_id" in body
        assert "last_seen_at" in body

    async def test_returns_404_when_not_found(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.heartbeat = AsyncMock(side_effect=NotFoundError("nope"))
        r = await ac.post("/v1/agents/no-tenant/no-agent/heartbeat")
        assert r.status_code == 404

    async def test_calls_service_with_correct_ids(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        profile = _make_profile()
        profile.last_seen_at = datetime.now(UTC)
        mock_svc.heartbeat = AsyncMock(return_value=profile)
        await ac.post("/v1/agents/my-tenant/my-bot/heartbeat")
        mock_svc.heartbeat.assert_awaited_once_with("my-tenant", "my-bot")
