"""Integration: AgentRegistryService end-to-end business logic."""
from __future__ import annotations

from datetime import UTC, datetime
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
    tenant_id: str = "tenant-acme",
    agent_id: str = "agent-1",
    name: str = "Bot",
) -> AgentProfile:
    return AgentProfile(
        id=uuid4(),
        tenant_id=tenant_id,
        agent_id=agent_id,
        name=name,
        version="1.0",
    )


def _session_for_create(existing: AgentProfile | None) -> MagicMock:
    """execute called once for duplicate check."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _session_for_get(profile: AgentProfile | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = profile
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _session_with_list(profiles: list[AgentProfile]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = profiles
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    async def test_register_new_agent_succeeds(self) -> None:
        session = _session_for_create(None)
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        profile = await svc.create(
            AgentProfileCreate(
                tenant_id="acme",
                agent_id="invoice-bot",
                name="Invoice Bot",
                version="1.2",
                capabilities=["read_invoices", "send_email"],
                tags={"team": "finance"},
            )
        )

        assert profile.tenant_id == "acme"
        assert profile.agent_id == "invoice-bot"
        assert profile.name == "Invoice Bot"
        assert profile.version == "1.2"
        assert "read_invoices" in profile.capabilities
        assert profile.tags["team"] == "finance"
        assert profile.is_active is True

    async def test_register_duplicate_raises_conflict(self) -> None:
        existing = _make_profile()
        session = _session_for_create(existing)
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        with pytest.raises(ConflictError):
            await svc.create(
                AgentProfileCreate(
                    tenant_id="tenant-acme",
                    agent_id="agent-1",
                    name="Dup",
                    version="1.0",
                )
            )

    async def test_same_agent_id_different_tenant_allowed(self) -> None:
        """Duplicate check is (tenant_id, agent_id) — different tenant is fine."""
        session = _session_for_create(None)
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        profile = await svc.create(
            AgentProfileCreate(
                tenant_id="other-tenant",
                agent_id="agent-1",
                name="Bot",
                version="1.0",
            )
        )
        assert profile.tenant_id == "other-tenant"


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


class TestLookup:
    async def test_get_by_id_returns_correct_profile(self) -> None:
        profile = _make_profile()
        session = _session_for_get(profile)
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        result = await svc.get(profile.id)
        assert result.id == profile.id

    async def test_get_missing_id_raises_not_found(self) -> None:
        session = _session_for_get(None)
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        with pytest.raises(NotFoundError):
            await svc.get(uuid4())

    async def test_get_by_agent_id_returns_profile(self) -> None:
        profile = _make_profile(tenant_id="acme", agent_id="bot-x")
        session = _session_for_get(profile)
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        result = await svc.get_by_agent_id("acme", "bot-x")
        assert result.agent_id == "bot-x"

    async def test_get_by_agent_id_missing_raises_not_found(self) -> None:
        session = _session_for_get(None)
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        with pytest.raises(NotFoundError):
            await svc.get_by_agent_id("acme", "ghost")


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


class TestListing:
    async def test_list_returns_all_profiles_for_tenant(self) -> None:
        profiles = [_make_profile(agent_id=f"bot-{i}") for i in range(5)]
        session = _session_with_list(profiles)
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        result = await svc.list_for_tenant("tenant-acme")
        assert len(result) == 5

    async def test_list_returns_empty_for_unknown_tenant(self) -> None:
        session = _session_with_list([])
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        result = await svc.list_for_tenant("unknown")
        assert result == []


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class TestUpdate:
    async def test_update_name_persists(self) -> None:
        profile = _make_profile(name="old-name")
        session = _session_for_get(profile)
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        result = await svc.update(profile.id, AgentProfileUpdate(name="new-name"))
        assert result.name == "new-name"

    async def test_update_capabilities_replaces(self) -> None:
        profile = _make_profile()
        profile.capabilities = ["old-cap"]
        session = _session_for_get(profile)
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        result = await svc.update(profile.id, AgentProfileUpdate(capabilities=["new-cap"]))
        assert result.capabilities == ["new-cap"]

    async def test_deactivate_via_update(self) -> None:
        profile = _make_profile()
        session = _session_for_get(profile)
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        result = await svc.update(profile.id, AgentProfileUpdate(is_active=False))
        assert result.is_active is False

    async def test_update_missing_profile_raises_not_found(self) -> None:
        session = _session_for_get(None)
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        with pytest.raises(NotFoundError):
            await svc.update(uuid4(), AgentProfileUpdate(name="x"))


# ---------------------------------------------------------------------------
# Soft-delete
# ---------------------------------------------------------------------------


class TestSoftDelete:
    async def test_delete_sets_inactive(self) -> None:
        profile = _make_profile()
        session = _session_for_get(profile)
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        await svc.delete(profile.id)
        assert profile.is_active is False

    async def test_delete_commits(self) -> None:
        profile = _make_profile()
        session = _session_for_get(profile)
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        await svc.delete(profile.id)
        session.commit.assert_awaited_once()

    async def test_delete_missing_raises_not_found(self) -> None:
        session = _session_for_get(None)
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        with pytest.raises(NotFoundError):
            await svc.delete(uuid4())


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:
    async def test_heartbeat_sets_last_seen_at(self) -> None:
        profile = _make_profile()
        assert profile.last_seen_at is None
        session = _session_for_get(profile)
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        before = datetime.now(UTC)
        result = await svc.heartbeat("tenant-acme", "agent-1")
        after = datetime.now(UTC)

        assert result.last_seen_at is not None
        assert before <= result.last_seen_at <= after

    async def test_heartbeat_commits(self) -> None:
        profile = _make_profile()
        session = _session_for_get(profile)
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        await svc.heartbeat("tenant-acme", "agent-1")
        session.commit.assert_awaited_once()

    async def test_heartbeat_unknown_agent_raises_not_found(self) -> None:
        session = _session_for_get(None)
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        with pytest.raises(NotFoundError):
            await svc.heartbeat("tenant-acme", "ghost-agent")

    async def test_successive_heartbeats_advance_timestamp(self) -> None:
        profile = _make_profile()
        results = [MagicMock(), MagicMock()]
        results[0].scalar_one_or_none.return_value = profile
        results[1].scalar_one_or_none.return_value = profile
        session = MagicMock()
        session.execute = AsyncMock(side_effect=results)
        session.add = MagicMock()
        session.commit = AsyncMock()
        svc = AgentRegistryService(session)  # type: ignore[arg-type]

        await svc.heartbeat("tenant-acme", "agent-1")
        first = profile.last_seen_at

        await svc.heartbeat("tenant-acme", "agent-1")
        second = profile.last_seen_at

        assert second >= first  # type: ignore[operator]
