"""Module 5 — Sentinel: model tests."""
from __future__ import annotations

from uuid import UUID, uuid4

from common.models.policy import Policy
from common.models.sentinel import SentinelAlert


class TestSentinelAlertModel:
    def test_construction(self) -> None:
        alert = SentinelAlert(
            id=uuid4(),
            tenant_id="tenant-acme",
            agent_id="agent-1",
            sentinel_type="tool_misuse",
            severity="high",
            message="Tool blocked",
        )
        assert alert.tenant_id == "tenant-acme"
        assert alert.agent_id == "agent-1"
        assert alert.sentinel_type == "tool_misuse"
        assert alert.severity == "high"
        assert alert.message == "Tool blocked"

    def test_id_is_uuid(self) -> None:
        uid = uuid4()
        alert = SentinelAlert(
            id=uid,
            tenant_id="t",
            agent_id="a",
            sentinel_type="drift",
            severity="low",
            message="msg",
        )
        assert alert.id == uid
        assert isinstance(alert.id, UUID)

    def test_is_resolved_defaults_to_false(self) -> None:
        alert = SentinelAlert(
            id=uuid4(),
            tenant_id="t",
            agent_id="a",
            sentinel_type="drift",
            severity="low",
            message="m",
        )
        assert alert.is_resolved is False

    def test_details_defaults_to_empty_dict(self) -> None:
        alert = SentinelAlert(
            id=uuid4(),
            tenant_id="t",
            agent_id="a",
            sentinel_type="drift",
            severity="low",
            message="m",
        )
        assert alert.details == {}

    def test_event_id_can_be_none(self) -> None:
        alert = SentinelAlert(
            id=uuid4(),
            tenant_id="t",
            agent_id="a",
            sentinel_type="drift",
            severity="low",
            message="m",
        )
        assert alert.event_id is None

    def test_event_id_can_be_set(self) -> None:
        eid = uuid4()
        alert = SentinelAlert(
            id=uuid4(),
            event_id=eid,
            tenant_id="t",
            agent_id="a",
            sentinel_type="drift",
            severity="low",
            message="m",
        )
        assert alert.event_id == eid

    def test_action_taken_defaults_to_none(self) -> None:
        alert = SentinelAlert(
            id=uuid4(),
            tenant_id="t",
            agent_id="a",
            sentinel_type="drift",
            severity="low",
            message="m",
        )
        assert alert.action_taken is None

    def test_resolved_at_defaults_to_none(self) -> None:
        alert = SentinelAlert(
            id=uuid4(),
            tenant_id="t",
            agent_id="a",
            sentinel_type="drift",
            severity="low",
            message="m",
        )
        assert alert.resolved_at is None

    def test_details_can_be_provided(self) -> None:
        data = {"key": "val", "count": 3}
        alert = SentinelAlert(
            id=uuid4(),
            tenant_id="t",
            agent_id="a",
            sentinel_type="drift",
            severity="low",
            message="m",
            details=data,
        )
        assert alert.details == data


class TestPolicyModel:
    def test_construction(self) -> None:
        policy = Policy(
            id=uuid4(),
            tenant_id="tenant-acme",
            name="Block Tool Misuse",
            sentinel_type="tool_misuse",
            severity="high",
            action="block_tool_call",
        )
        assert policy.name == "Block Tool Misuse"
        assert policy.sentinel_type == "tool_misuse"
        assert policy.action == "block_tool_call"

    def test_id_is_uuid(self) -> None:
        pid = uuid4()
        policy = Policy(
            id=pid,
            tenant_id="t",
            name="p",
            sentinel_type="drift",
            severity="low",
            action="warn",
        )
        assert policy.id == pid
        assert isinstance(policy.id, UUID)

    def test_is_active_defaults_to_true(self) -> None:
        policy = Policy(
            id=uuid4(),
            tenant_id="t",
            name="p",
            sentinel_type="drift",
            severity="low",
            action="warn",
        )
        assert policy.is_active is True

    def test_description_defaults_to_empty_string(self) -> None:
        policy = Policy(
            id=uuid4(),
            tenant_id="t",
            name="p",
            sentinel_type="drift",
            severity="low",
            action="warn",
        )
        assert policy.description == ""

    def test_config_defaults_to_empty_dict(self) -> None:
        policy = Policy(
            id=uuid4(),
            tenant_id="t",
            name="p",
            sentinel_type="drift",
            severity="low",
            action="warn",
        )
        assert policy.config == {}

    def test_custom_config(self) -> None:
        cfg = {"threshold": 0.8, "window_seconds": 300}
        policy = Policy(
            id=uuid4(),
            tenant_id="t",
            name="p",
            sentinel_type="drift",
            severity="low",
            action="warn",
            config=cfg,
        )
        assert policy.config == cfg
