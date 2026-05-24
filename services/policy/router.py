"""Policy evaluation HTTP routes."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from common.exceptions import NotFoundError
from common.schemas.policy import (
    PolicyEvaluateRequest,
    PolicyEvaluationResult,
    PolicyUpdate,
)
from common.schemas.sentinel import PolicyResponse

from .deps import get_policy_evaluator
from .service import PolicyEvaluatorService

router = APIRouter(prefix="/v1/policies", tags=["policies"])


@router.get("/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: UUID,
    service: Annotated[PolicyEvaluatorService, Depends(get_policy_evaluator)],
) -> PolicyResponse:
    try:
        policy = await service.get_policy(policy_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return PolicyResponse.model_validate(policy)


@router.put("/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: UUID,
    update: PolicyUpdate,
    service: Annotated[PolicyEvaluatorService, Depends(get_policy_evaluator)],
) -> PolicyResponse:
    try:
        policy = await service.update_policy(policy_id, update)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return PolicyResponse.model_validate(policy)


@router.post("/evaluate", response_model=PolicyEvaluationResult)
async def evaluate_policies(
    request: PolicyEvaluateRequest,
    service: Annotated[PolicyEvaluatorService, Depends(get_policy_evaluator)],
) -> PolicyEvaluationResult:
    return await service.evaluate(request)
