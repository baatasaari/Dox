"""Module 10 — Policy Engine: service layer tests."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common.exceptions import NotFoundError
from common.models.policy import Policy
from common.schemas.enums import InterventionAction, SentinelType, Severity
from common.schemas.policy import PolicyEvaluateRequest, PolicyUpdate
from services.policy.service import _ACTION_RANK, _BLOCK_THRESHOLD, PolicyEvaluatorService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_policy(
    *,
    tenant_id: str = "tenant-acme",
    sentinel_type: str = SentinelType.tool_misuse,
    severity: str = Severity.high,
    action: str = InterventionAction.block_tool_call,
    is_active: bool = True,
    name: str = "default",
) -> Policy:
    return Policy(
        id=uuid4(),
        tenant_id=tenant_id,
        name=name,
        sentinel_type=sentinel_type,
        severity=severity,
        action=action,
        is_active=is_active,
    )


def _scalar_result(obj: object) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


def _scalars_result(items: list[Any]) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _make_session(*execute_results: MagicMock) -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=list(execute_results))
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Action / severity ranking constants
# ---------------------------------------------------------------------------


class TestActionRankConstants:
    def test_allow_is_lowest(self) -> None:
        assert _ACTION_RANK[InterventionAction.allow] == 0

    def test_terminate_is_highest(self) -> None:
        assert _ACTION_RANK[InterventionAction.terminate_execution] == 9

    def test_block_is_at_threshold(self) -> None:
        assert _ACTION_RANK[InterventionAction.block_tool_call] == _BLOCK_THRESHOLD

    def test_warn_below_threshold(self) -> None:
        assert _ACTION_RANK[InterventionAction.warn] < _BLOCK_THRESHOLD

    def test_pause_agent_above_threshold(self) -> None:
        assert _ACTION_RANK[InterventionAction.pause_agent] > _BLOCK_THRESHOLD


# ---------------------------------------------------------------------------
# _policy_matches
# ---------------------------------------------------------------------------


class TestPolicyMatches:
    def test_exact_severity_match(self) -> None:
        policy = _make_policy(severity=Severity.high)
        req = PolicyEvaluateRequest(
            tenant_id="t",
            sentinel_type=SentinelType.tool_misuse,
            severity=Severity.high,
        )
        assert PolicyEvaluatorService._policy_matches(policy, req) is True

    def test_request_severity_higher_than_policy(self) -> None:
        policy = _make_policy(severity=Severity.low)
        req = PolicyEvaluateRequest(
            tenant_id="t",
            sentinel_type=SentinelType.tool_misuse,
            severity=Severity.critical,
        )
        assert PolicyEvaluatorService._policy_matches(policy, req) is True

    def test_request_severity_lower_than_policy(self) -> None:
        policy = _make_policy(severity=Severity.high)
        req = PolicyEvaluateRequest(
            tenant_id="t",
            sentinel_type=SentinelType.tool_misuse,
            severity=Severity.low,
        )
        assert PolicyEvaluatorService._policy_matches(policy, req) is False


# ---------------------------------------------------------------------------
# _winning_action
# ---------------------------------------------------------------------------


class TestWinningAction:
    def test_empty_policies_returns_allow(self) -> None:
        assert PolicyEvaluatorService._winning_action([]) == InterventionAction.allow

    def test_single_policy_returns_its_action(self) -> None:
        policy = _make_policy(action=InterventionAction.warn)
        assert PolicyEvaluatorService._winning_action([policy]) == InterventionAction.warn

    def test_most_restrictive_action_wins(self) -> None:
        policies = [
            _make_policy(action=InterventionAction.warn),
            _make_policy(action=InterventionAction.terminate_execution),
            _make_policy(action=InterventionAction.block_tool_call),
        ]
        assert (
            PolicyEvaluatorService._winning_action(policies)
            == InterventionAction.terminate_execution
        )

    def test_all_same_action_returns_that_action(self) -> None:
        policies = [_make_policy(action=InterventionAction.redact) for _ in range(3)]
        assert PolicyEvaluatorService._winning_action(policies) == InterventionAction.redact


# ---------------------------------------------------------------------------
# get_policy
# ---------------------------------------------------------------------------


class TestGetPolicy:
    async def test_returns_policy_when_found(self) -> None:
        policy = _make_policy()
        session = _make_session(_scalar_result(policy))
        svc = PolicyEvaluatorService(session)  # type: ignore[arg-type]
        result = await svc.get_policy(policy.id)
        assert result is policy

    async def test_raises_not_found_when_missing(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = PolicyEvaluatorService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.get_policy(uuid4())


# ---------------------------------------------------------------------------
# update_policy
# ---------------------------------------------------------------------------


class TestUpdatePolicy:
    async def test_updates_name(self) -> None:
        policy = _make_policy(name="old")
        session = _make_session(_scalar_result(policy))
        svc = PolicyEvaluatorService(session)  # type: ignore[arg-type]
        result = await svc.update_policy(policy.id, PolicyUpdate(name="new"))
        assert result.name == "new"
        session.commit.assert_awaited_once()

    async def test_updates_action(self) -> None:
        policy = _make_policy(action=InterventionAction.warn)
        session = _make_session(_scalar_result(policy))
        svc = PolicyEvaluatorService(session)  # type: ignore[arg-type]
        result = await svc.update_policy(
            policy.id, PolicyUpdate(action=InterventionAction.terminate_execution)
        )
        assert result.action == InterventionAction.terminate_execution

    async def test_deactivates_via_update(self) -> None:
        policy = _make_policy(is_active=True)
        session = _make_session(_scalar_result(policy))
        svc = PolicyEvaluatorService(session)  # type: ignore[arg-type]
        result = await svc.update_policy(policy.id, PolicyUpdate(is_active=False))
        assert result.is_active is False

    async def test_reactivates_via_update(self) -> None:
        policy = _make_policy(is_active=False)
        session = _make_session(_scalar_result(policy))
        svc = PolicyEvaluatorService(session)  # type: ignore[arg-type]
        result = await svc.update_policy(policy.id, PolicyUpdate(is_active=True))
        assert result.is_active is True

    async def test_raises_not_found_when_missing(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = PolicyEvaluatorService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.update_policy(uuid4(), PolicyUpdate(name="x"))

    async def test_none_fields_not_applied(self) -> None:
        policy = _make_policy(name="unchanged")
        session = _make_session(_scalar_result(policy))
        svc = PolicyEvaluatorService(session)  # type: ignore[arg-type]
        result = await svc.update_policy(policy.id, PolicyUpdate())
        assert result.name == "unchanged"


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


class TestEvaluate:
    async def test_no_policies_returns_allow(self) -> None:
        session = _make_session(_scalars_result([]))
        svc = PolicyEvaluatorService(session)  # type: ignore[arg-type]
        result = await svc.evaluate(
            PolicyEvaluateRequest(
                tenant_id="t",
                sentinel_type=SentinelType.tool_misuse,
                severity=Severity.high,
            )
        )
        assert result.action == InterventionAction.allow
        assert result.matched_count == 0
        assert result.is_blocked is False

    async def test_matching_policy_determines_action(self) -> None:
        policy = _make_policy(
            severity=Severity.medium, action=InterventionAction.block_tool_call
        )
        session = _make_session(_scalars_result([policy]))
        svc = PolicyEvaluatorService(session)  # type: ignore[arg-type]
        result = await svc.evaluate(
            PolicyEvaluateRequest(
                tenant_id="tenant-acme",
                sentinel_type=SentinelType.tool_misuse,
                severity=Severity.high,
            )
        )
        assert result.action == InterventionAction.block_tool_call
        assert result.matched_count == 1
        assert result.is_blocked is True

    async def test_severity_too_low_not_matched(self) -> None:
        policy = _make_policy(
            severity=Severity.critical, action=InterventionAction.terminate_execution
        )
        session = _make_session(_scalars_result([policy]))
        svc = PolicyEvaluatorService(session)  # type: ignore[arg-type]
        result = await svc.evaluate(
            PolicyEvaluateRequest(
                tenant_id="tenant-acme",
                sentinel_type=SentinelType.tool_misuse,
                severity=Severity.low,
            )
        )
        assert result.action == InterventionAction.allow
        assert result.matched_count == 0

    async def test_most_restrictive_wins_among_matches(self) -> None:
        policies = [
            _make_policy(severity=Severity.low, action=InterventionAction.warn, name="p1"),
            _make_policy(
                severity=Severity.low,
                action=InterventionAction.terminate_execution,
                name="p2",
            ),
        ]
        session = _make_session(_scalars_result(policies))
        svc = PolicyEvaluatorService(session)  # type: ignore[arg-type]
        result = await svc.evaluate(
            PolicyEvaluateRequest(
                tenant_id="tenant-acme",
                sentinel_type=SentinelType.tool_misuse,
                severity=Severity.medium,
            )
        )
        assert result.action == InterventionAction.terminate_execution
        assert result.matched_count == 2

    async def test_is_blocked_true_for_terminate(self) -> None:
        policy = _make_policy(
            severity=Severity.low, action=InterventionAction.terminate_execution
        )
        session = _make_session(_scalars_result([policy]))
        svc = PolicyEvaluatorService(session)  # type: ignore[arg-type]
        result = await svc.evaluate(
            PolicyEvaluateRequest(
                tenant_id="t",
                sentinel_type=SentinelType.tool_misuse,
                severity=Severity.high,
            )
        )
        assert result.is_blocked is True

    async def test_is_blocked_false_for_warn(self) -> None:
        policy = _make_policy(severity=Severity.low, action=InterventionAction.warn)
        session = _make_session(_scalars_result([policy]))
        svc = PolicyEvaluatorService(session)  # type: ignore[arg-type]
        result = await svc.evaluate(
            PolicyEvaluateRequest(
                tenant_id="t",
                sentinel_type=SentinelType.tool_misuse,
                severity=Severity.high,
            )
        )
        assert result.is_blocked is False

    async def test_matched_policies_list_populated(self) -> None:
        policy = _make_policy(
            severity=Severity.low, action=InterventionAction.warn, name="my-policy"
        )
        session = _make_session(_scalars_result([policy]))
        svc = PolicyEvaluatorService(session)  # type: ignore[arg-type]
        result = await svc.evaluate(
            PolicyEvaluateRequest(
                tenant_id="t",
                sentinel_type=SentinelType.tool_misuse,
                severity=Severity.high,
            )
        )
        assert len(result.matched_policies) == 1
        assert result.matched_policies[0].name == "my-policy"

    async def test_result_echoes_request_fields(self) -> None:
        session = _make_session(_scalars_result([]))
        svc = PolicyEvaluatorService(session)  # type: ignore[arg-type]
        result = await svc.evaluate(
            PolicyEvaluateRequest(
                tenant_id="my-tenant",
                sentinel_type=SentinelType.drift,
                severity=Severity.medium,
            )
        )
        assert result.tenant_id == "my-tenant"
        assert result.sentinel_type == SentinelType.drift
        assert result.severity == Severity.medium
