"""Module 11 — Agent Registry: service layer tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common.exceptions import ConflictError, NotFoundError
from common.models.agent import AgentProfile
from common.schemas.agent import AgentProfileCreate, AgentProfileUpdate
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
    return AgentProfile(
        id=uuid4(),
        tenant_id=tenant_id,
        agent_id=agent_id,
        name=name,
        version=version,
    )


def _scalar_result(obj: object) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


def _scalars_result(items: list[object]) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _make_session(*execute_results: MagicMock) -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=list(execute_results))
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class TestCreateAgent:
    async def test_creates_profile_when_not_duplicate(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        profile = await svc.create(
            AgentProfileCreate(tenant_id="acme", agent_id="bot", name="Bot", version="1.0")
        )

        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        assert profile.agent_id == "bot"

    async def test_raises_conflict_for_duplicate(self) -> None:
        existing = _make_profile()
        session = _make_session(_scalar_result(existing))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        with pytest.raises(ConflictError):
            await svc.create(
                AgentProfileCreate(
                    tenant_id="tenant-acme", agent_id="agent-1", name="Bot", version="1.0"
                )
            )

    async def test_capabilities_stored(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        profile = await svc.create(
            AgentProfileCreate(
                tenant_id="acme",
                agent_id="bot",
                name="Bot",
                version="1.0",
                capabilities=["read", "write"],
            )
        )
        assert profile.capabilities == ["read", "write"]

    async def test_tags_stored(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        profile = await svc.create(
            AgentProfileCreate(
                tenant_id="acme",
                agent_id="bot",
                name="Bot",
                version="1.0",
                tags={"env": "prod"},
            )
        )
        assert profile.tags == {"env": "prod"}

    async def test_description_stored(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        profile = await svc.create(
            AgentProfileCreate(
                tenant_id="acme",
                agent_id="bot",
                name="Bot",
                version="1.0",
                description="handles invoicing",
            )
        )
        assert profile.description == "handles invoicing"


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


class TestGetAgent:
    async def test_returns_profile_when_found(self) -> None:
        profile = _make_profile()
        session = _make_session(_scalar_result(profile))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]
        result = await svc.get(profile.id)
        assert result is profile

    async def test_raises_not_found_when_missing(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.get(uuid4())


# ---------------------------------------------------------------------------
# get_by_agent_id
# ---------------------------------------------------------------------------


class TestGetByAgentId:
    async def test_returns_profile(self) -> None:
        profile = _make_profile()
        session = _make_session(_scalar_result(profile))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]
        result = await svc.get_by_agent_id("tenant-acme", "agent-1")
        assert result is profile

    async def test_raises_not_found(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.get_by_agent_id("no-tenant", "no-agent")


# ---------------------------------------------------------------------------
# list_for_tenant
# ---------------------------------------------------------------------------


class TestListForTenant:
    async def test_returns_list(self) -> None:
        profiles = [_make_profile(agent_id=f"agent-{i}") for i in range(3)]
        session = _make_session(_scalars_result(profiles))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]
        result = await svc.list_for_tenant("tenant-acme")
        assert len(result) == 3

    async def test_returns_empty_list(self) -> None:
        session = _make_session(_scalars_result([]))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]
        result = await svc.list_for_tenant("no-tenant")
        assert result == []


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


class TestUpdateAgent:
    async def test_updates_name(self) -> None:
        profile = _make_profile(name="old")
        session = _make_session(_scalar_result(profile))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]
        result = await svc.update(profile.id, AgentProfileUpdate(name="new"))
        assert result.name == "new"
        session.commit.assert_awaited_once()

    async def test_updates_version(self) -> None:
        profile = _make_profile(version="1.0")
        session = _make_session(_scalar_result(profile))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]
        result = await svc.update(profile.id, AgentProfileUpdate(version="2.0"))
        assert result.version == "2.0"

    async def test_deactivates_via_update(self) -> None:
        profile = _make_profile()
        session = _make_session(_scalar_result(profile))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]
        result = await svc.update(profile.id, AgentProfileUpdate(is_active=False))
        assert result.is_active is False

    async def test_none_fields_not_applied(self) -> None:
        profile = _make_profile(name="unchanged")
        session = _make_session(_scalar_result(profile))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]
        result = await svc.update(profile.id, AgentProfileUpdate())
        assert result.name == "unchanged"

    async def test_raises_not_found_when_missing(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.update(uuid4(), AgentProfileUpdate(name="x"))

    async def test_updates_capabilities(self) -> None:
        profile = _make_profile()
        session = _make_session(_scalar_result(profile))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]
        result = await svc.update(profile.id, AgentProfileUpdate(capabilities=["read"]))
        assert result.capabilities == ["read"]

    async def test_updates_tags(self) -> None:
        profile = _make_profile()
        session = _make_session(_scalar_result(profile))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]
        result = await svc.update(profile.id, AgentProfileUpdate(tags={"env": "prod"}))
        assert result.tags == {"env": "prod"}


# ---------------------------------------------------------------------------
# delete (soft deactivate)
# ---------------------------------------------------------------------------


class TestDeleteAgent:
    async def test_sets_is_active_false(self) -> None:
        profile = _make_profile()
        session = _make_session(_scalar_result(profile))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]
        await svc.delete(profile.id)
        assert profile.is_active is False
        session.commit.assert_awaited_once()

    async def test_raises_not_found_when_missing(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.delete(uuid4())


# ---------------------------------------------------------------------------
# heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:
    async def test_updates_last_seen_at(self) -> None:
        profile = _make_profile()
        session = _make_session(_scalar_result(profile))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]
        result = await svc.heartbeat("tenant-acme", "agent-1")
        assert result.last_seen_at is not None
        session.commit.assert_awaited_once()

    async def test_raises_not_found_for_unknown_agent(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.heartbeat("tenant-acme", "ghost")

    async def test_returns_profile(self) -> None:
        profile = _make_profile()
        session = _make_session(_scalar_result(profile))
        svc = AgentRegistryService(session)  # type: ignore[arg-type]
        result = await svc.heartbeat("tenant-acme", "agent-1")
        assert result is profile
