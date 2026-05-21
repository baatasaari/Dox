"""Module 5 — Sentinel: schema tests."""
from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from common.schemas.enums import InterventionAction, SentinelType, Severity
from common.schemas.sentinel import (
    AlertListResponse,
    PolicyCreate,
    PolicyListResponse,
    ResolveAlertRequest,
    SentinelAlertCreate,
    SentinelAlertResponse,
)


class TestSentinelAlertCreate:
    def test_valid_full(self) -> None:
        eid = uuid4()
        s = SentinelAlertCreate(
            event_id=eid,
            tenant_id="tenant-acme",
            agent_id="agent-1",
            sentinel_type=SentinelType.tool_misuse,
            severity=Severity.high,
            message="Tool blocked",
            details={"tool": "bash"},
        )
        assert s.event_id == eid
        assert s.sentinel_type == SentinelType.tool_misuse
        assert s.severity == Severity.high

    def test_event_id_is_optional(self) -> None:
        s = SentinelAlertCreate(
            tenant_id="t",
            agent_id="a",
            sentinel_type=SentinelType.drift,
            severity=Severity.low,
            message="drift detected",
        )
        assert s.event_id is None

    def test_details_defaults_to_empty_dict(self) -> None:
        s = SentinelAlertCreate(
            tenant_id="t",
            agent_id="a",
            sentinel_type=SentinelType.drift,
            severity=Severity.low,
            message="msg",
        )
        assert s.details == {}

    def test_empty_message_raises(self) -> None:
        with pytest.raises(ValidationError):
            SentinelAlertCreate(
                tenant_id="t",
                agent_id="a",
                sentinel_type=SentinelType.drift,
                severity=Severity.low,
                message="",
            )

    def test_missing_required_fields_raise(self) -> None:
        with pytest.raises(ValidationError):
            SentinelAlertCreate(tenant_id="t", agent_id="a")  # type: ignore[call-arg]


class TestResolveAlertRequest:
    def test_valid_action(self) -> None:
        r = ResolveAlertRequest(action=InterventionAction.warn)
        assert r.action == InterventionAction.warn

    def test_all_intervention_actions_accepted(self) -> None:
        for action in InterventionAction:
            r = ResolveAlertRequest(action=action)
            assert r.action == action

    def test_missing_action_raises(self) -> None:
        with pytest.raises(ValidationError):
            ResolveAlertRequest()  # type: ignore[call-arg]

    def test_invalid_action_raises(self) -> None:
        with pytest.raises(ValidationError):
            ResolveAlertRequest(action="explode")  # type: ignore[arg-type]


class TestSentinelAlertResponse:
    def test_valid_construction(self) -> None:
        r = SentinelAlertResponse(
            id=uuid4(),
            event_id=None,
            tenant_id="t",
            agent_id="a",
            sentinel_type=SentinelType.drift,
            severity=Severity.medium,
            message="drift",
            details={},
            action_taken=None,
            is_resolved=False,
            resolved_at=None,
        )
        assert r.is_resolved is False
        assert r.created_at is None

    def test_model_validate_from_orm(self) -> None:
        from common.models.sentinel import SentinelAlert

        alert = SentinelAlert(
            id=uuid4(),
            tenant_id="tenant-acme",
            agent_id="agent-1",
            sentinel_type="tool_misuse",
            severity="high",
            message="Tool blocked",
        )
        resp = SentinelAlertResponse.model_validate(alert)
        assert resp.tenant_id == "tenant-acme"
        assert resp.severity == Severity.high
        assert resp.is_resolved is False


class TestPolicyCreate:
    def test_valid_full(self) -> None:
        p = PolicyCreate(
            tenant_id="t",
            name="Block misuse",
            description="Block tool misuse",
            sentinel_type=SentinelType.tool_misuse,
            severity=Severity.high,
            action=InterventionAction.block_tool_call,
            config={"threshold": 3},
        )
        assert p.name == "Block misuse"
        assert p.config == {"threshold": 3}

    def test_description_defaults_to_empty(self) -> None:
        p = PolicyCreate(
            tenant_id="t",
            name="p",
            sentinel_type=SentinelType.drift,
            severity=Severity.low,
            action=InterventionAction.warn,
        )
        assert p.description == ""

    def test_config_defaults_to_empty_dict(self) -> None:
        p = PolicyCreate(
            tenant_id="t",
            name="p",
            sentinel_type=SentinelType.drift,
            severity=Severity.low,
            action=InterventionAction.warn,
        )
        assert p.config == {}

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            PolicyCreate(
                tenant_id="t",
                name="",
                sentinel_type=SentinelType.drift,
                severity=Severity.low,
                action=InterventionAction.warn,
            )


class TestAlertListResponse:
    def test_construction(self) -> None:
        r = AlertListResponse(alerts=[], total=0)
        assert r.total == 0
        assert r.alerts == []

    def test_total_with_items(self) -> None:
        alert = SentinelAlertResponse(
            id=uuid4(),
            event_id=None,
            tenant_id="t",
            agent_id="a",
            sentinel_type=SentinelType.drift,
            severity=Severity.low,
            message="m",
            details={},
            action_taken=None,
            is_resolved=False,
            resolved_at=None,
        )
        r = AlertListResponse(alerts=[alert], total=1)
        assert r.total == 1
        assert len(r.alerts) == 1


class TestPolicyListResponse:
    def test_construction(self) -> None:
        r = PolicyListResponse(policies=[], total=0)
        assert r.total == 0
