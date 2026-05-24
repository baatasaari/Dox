"""Policy evaluation engine."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import NotFoundError
from common.models.policy import Policy
from common.schemas.enums import InterventionAction, Severity
from common.schemas.policy import (
    MatchedPolicy,
    PolicyEvaluateRequest,
    PolicyEvaluationResult,
    PolicyUpdate,
)

_ACTION_RANK: dict[str, int] = {
    InterventionAction.allow: 0,
    InterventionAction.warn: 1,
    InterventionAction.redact: 2,
    InterventionAction.request_human_review: 3,
    InterventionAction.block_tool_call: 4,
    InterventionAction.pause_agent: 5,
    InterventionAction.rollback_memory_write: 6,
    InterventionAction.force_safe_response: 7,
    InterventionAction.isolate_agent: 8,
    InterventionAction.terminate_execution: 9,
}

_SEVERITY_RANK: dict[str, int] = {
    Severity.low: 0,
    Severity.medium: 1,
    Severity.high: 2,
    Severity.critical: 3,
}

# Actions at or above this rank are considered blocking.
_BLOCK_THRESHOLD = _ACTION_RANK[InterventionAction.block_tool_call]


class PolicyEvaluatorService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_policy(self, policy_id: UUID) -> Policy:
        result = await self._session.execute(
            select(Policy).where(Policy.id == policy_id)
        )
        policy = result.scalar_one_or_none()
        if policy is None:
            raise NotFoundError(f"Policy {policy_id} not found")
        return policy

    async def update_policy(self, policy_id: UUID, update: PolicyUpdate) -> Policy:
        policy = await self.get_policy(policy_id)
        patch = update.model_dump(exclude_none=True)
        for field, value in patch.items():
            setattr(policy, field, value)
        await self._session.commit()
        return policy

    async def evaluate(self, request: PolicyEvaluateRequest) -> PolicyEvaluationResult:
        result = await self._session.execute(
            select(Policy).where(
                and_(
                    Policy.tenant_id == request.tenant_id,
                    Policy.sentinel_type == request.sentinel_type,
                    Policy.is_active.is_(True),
                )
            )
        )
        candidates = list(result.scalars().all())
        matched = [p for p in candidates if self._policy_matches(p, request)]
        action = self._winning_action(matched)
        return PolicyEvaluationResult(
            tenant_id=request.tenant_id,
            sentinel_type=request.sentinel_type,
            severity=request.severity,
            matched_count=len(matched),
            matched_policies=[
                MatchedPolicy(id=p.id, name=p.name, action=p.action) for p in matched
            ],
            action=action,
            is_blocked=_ACTION_RANK.get(str(action), 0) >= _BLOCK_THRESHOLD,
        )

    @staticmethod
    def _policy_matches(policy: Policy, request: PolicyEvaluateRequest) -> bool:
        return _SEVERITY_RANK.get(str(request.severity), 0) >= _SEVERITY_RANK.get(
            str(policy.severity), 0
        )

    @staticmethod
    def _winning_action(policies: list[Policy]) -> InterventionAction:
        if not policies:
            return InterventionAction.allow
        winner = max(policies, key=lambda p: _ACTION_RANK.get(str(p.action), 0))
        return InterventionAction(winner.action)
