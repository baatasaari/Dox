"""Module 10 — Policy Engine: schema tests."""
from __future__ import annotations

from uuid import uuid4

from common.schemas.enums import InterventionAction, SentinelType, Severity
from common.schemas.policy import (
    MatchedPolicy,
    PolicyEvaluateRequest,
    PolicyEvaluationResult,
    PolicyUpdate,
)


class TestPolicyUpdate:
    def test_all_fields_optional(self) -> None:
        u = PolicyUpdate()
        assert u.name is None
        assert u.description is None
        assert u.severity is None
        assert u.action is None
        assert u.is_active is None
        assert u.config is None

    def test_partial_update_only_name(self) -> None:
        u = PolicyUpdate(name="new name")
        assert u.name == "new name"
        assert u.action is None

    def test_is_active_can_be_set_false(self) -> None:
        u = PolicyUpdate(is_active=False)
        assert u.is_active is False

    def test_is_active_can_be_set_true(self) -> None:
        u = PolicyUpdate(is_active=True)
        assert u.is_active is True


class TestPolicyEvaluateRequest:
    def test_valid_request(self) -> None:
        req = PolicyEvaluateRequest(
            tenant_id="tenant-acme",
            sentinel_type=SentinelType.tool_misuse,
            severity=Severity.high,
        )
        assert req.tenant_id == "tenant-acme"
        assert req.sentinel_type == SentinelType.tool_misuse
        assert req.severity == Severity.high


class TestPolicyEvaluationResult:
    def test_blocked_when_action_is_block(self) -> None:
        result = PolicyEvaluationResult(
            tenant_id="t",
            sentinel_type=SentinelType.tool_misuse,
            severity=Severity.high,
            matched_count=1,
            matched_policies=[
                MatchedPolicy(
                    id=uuid4(),
                    name="block policy",
                    action=InterventionAction.block_tool_call,
                )
            ],
            action=InterventionAction.block_tool_call,
            is_blocked=True,
        )
        assert result.is_blocked is True

    def test_not_blocked_when_action_is_warn(self) -> None:
        result = PolicyEvaluationResult(
            tenant_id="t",
            sentinel_type=SentinelType.tool_misuse,
            severity=Severity.low,
            matched_count=1,
            matched_policies=[
                MatchedPolicy(
                    id=uuid4(),
                    name="warn policy",
                    action=InterventionAction.warn,
                )
            ],
            action=InterventionAction.warn,
            is_blocked=False,
        )
        assert result.is_blocked is False

    def test_no_matches_gives_allow(self) -> None:
        result = PolicyEvaluationResult(
            tenant_id="t",
            sentinel_type=SentinelType.drift,
            severity=Severity.low,
            matched_count=0,
            matched_policies=[],
            action=InterventionAction.allow,
            is_blocked=False,
        )
        assert result.matched_count == 0
        assert result.action == InterventionAction.allow
