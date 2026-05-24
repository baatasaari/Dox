"""Module 11 — Agent Registry: model tests."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from common.models.agent import AgentProfile


def _make_profile(**kw: object) -> AgentProfile:
    kw.setdefault("tenant_id", "tenant-acme")
    kw.setdefault("agent_id", "agent-1")
    kw.setdefault("name", "My Agent")
    kw.setdefault("version", "1.0")
    return AgentProfile(**kw)  # type: ignore[arg-type]


class TestAgentProfileDefaults:
    def test_is_active_defaults_true(self) -> None:
        profile = _make_profile()
        assert profile.is_active is True

    def test_capabilities_defaults_empty_list(self) -> None:
        profile = _make_profile()
        assert profile.capabilities == []

    def test_tags_defaults_empty_dict(self) -> None:
        profile = _make_profile()
        assert profile.tags == {}

    def test_last_seen_at_defaults_none(self) -> None:
        profile = _make_profile()
        assert profile.last_seen_at is None

    def test_description_defaults_none(self) -> None:
        profile = _make_profile()
        assert profile.description is None


class TestAgentProfileFields:
    def test_stores_tenant_id(self) -> None:
        profile = _make_profile(tenant_id="acme")
        assert profile.tenant_id == "acme"

    def test_stores_agent_id(self) -> None:
        profile = _make_profile(agent_id="bot-42")
        assert profile.agent_id == "bot-42"

    def test_stores_name(self) -> None:
        profile = _make_profile(name="Finance Bot")
        assert profile.name == "Finance Bot"

    def test_stores_version(self) -> None:
        profile = _make_profile(version="2.3.1")
        assert profile.version == "2.3.1"

    def test_stores_description(self) -> None:
        profile = _make_profile(description="handles invoicing")
        assert profile.description == "handles invoicing"

    def test_stores_capabilities(self) -> None:
        caps = ["read_db", "send_email"]
        profile = _make_profile(capabilities=caps)
        assert profile.capabilities == caps

    def test_stores_tags(self) -> None:
        tags = {"env": "prod", "team": "finance"}
        profile = _make_profile(tags=tags)
        assert profile.tags == tags

    def test_stores_last_seen_at(self) -> None:
        now = datetime.now(UTC)
        profile = _make_profile(last_seen_at=now)
        assert profile.last_seen_at == now

    def test_explicit_is_active_false(self) -> None:
        profile = _make_profile(is_active=False)
        assert profile.is_active is False


class TestAgentProfileCapabilitiesIsolation:
    def test_capabilities_list_is_independent(self) -> None:
        caps = ["read"]
        profile = _make_profile(capabilities=caps)
        caps.append("write")
        assert "write" not in profile.capabilities

    def test_two_profiles_do_not_share_capabilities(self) -> None:
        p1 = _make_profile(agent_id="a1")
        p2 = _make_profile(agent_id="a2")
        p1.capabilities.append("read")
        assert "read" not in p2.capabilities

    def test_two_profiles_do_not_share_tags(self) -> None:
        p1 = _make_profile(agent_id="a1")
        p2 = _make_profile(agent_id="a2")
        p1.tags["k"] = "v"
        assert "k" not in p2.tags


class TestAgentProfileId:
    def test_id_assigned_via_kwarg(self) -> None:
        uid = uuid4()
        profile = _make_profile(id=uid)
        assert profile.id == uid
