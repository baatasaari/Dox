"""Drift service HTTP routes — behavioral baseline management and drift analysis."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from common.exceptions import NotFoundError
from common.schemas.drift import (
    AnalyzeRequest,
    BaselineCreate,
    BaselineListResponse,
    BaselineResponse,
    DriftReportResponse,
)

from .deps import get_drift_service
from .service import DriftDetectionService

router = APIRouter(prefix="/v1/drift", tags=["drift"])


@router.post(
    "/baselines",
    status_code=status.HTTP_201_CREATED,
    response_model=BaselineResponse,
)
async def compute_baseline(
    create: BaselineCreate,
    service: Annotated[DriftDetectionService, Depends(get_drift_service)],
) -> BaselineResponse:
    baseline = await service.compute_baseline(create)
    return BaselineResponse.model_validate(baseline)


@router.get("/baselines", response_model=BaselineListResponse)
async def list_baselines(
    tenant_id: str,
    service: Annotated[DriftDetectionService, Depends(get_drift_service)],
    agent_id: Annotated[str | None, Query()] = None,
    active_only: Annotated[bool, Query()] = True,
) -> BaselineListResponse:
    baselines = await service.list_baselines(
        tenant_id, agent_id=agent_id, active_only=active_only
    )
    return BaselineListResponse(
        baselines=[BaselineResponse.model_validate(b) for b in baselines],
        total=len(baselines),
    )


@router.get("/baselines/{baseline_id}", response_model=BaselineResponse)
async def get_baseline(
    baseline_id: UUID,
    service: Annotated[DriftDetectionService, Depends(get_drift_service)],
) -> BaselineResponse:
    try:
        baseline = await service.get_baseline(baseline_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Baseline not found"
        )
    return BaselineResponse.model_validate(baseline)


@router.delete(
    "/baselines/{baseline_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def deactivate_baseline(
    baseline_id: UUID,
    service: Annotated[DriftDetectionService, Depends(get_drift_service)],
) -> None:
    try:
        await service.deactivate_baseline(baseline_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Baseline not found"
        )


@router.post("/analyze", response_model=DriftReportResponse)
async def analyze_drift(
    request: AnalyzeRequest,
    service: Annotated[DriftDetectionService, Depends(get_drift_service)],
) -> DriftReportResponse:
    return await service.analyze(request)
