"""Sentinel HTTP routes — alert management and policy CRUD."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from common.exceptions import NotFoundError
from common.schemas.enums import SentinelType, Severity
from common.schemas.sentinel import (
    AlertListResponse,
    PolicyCreate,
    PolicyListResponse,
    PolicyResponse,
    ResolveAlertRequest,
    SentinelAlertCreate,
    SentinelAlertResponse,
)

from .deps import get_sentinel_service
from .service import SentinelService

router = APIRouter(prefix="/v1/sentinel", tags=["sentinel"])


@router.post(
    "/alerts",
    status_code=status.HTTP_201_CREATED,
    response_model=SentinelAlertResponse,
)
async def create_alert(
    create: SentinelAlertCreate,
    service: Annotated[SentinelService, Depends(get_sentinel_service)],
) -> SentinelAlertResponse:
    alert = await service.create_alert(create)
    return SentinelAlertResponse.model_validate(alert)


@router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    tenant_id: str,
    service: Annotated[SentinelService, Depends(get_sentinel_service)],
    severity: Annotated[Severity | None, Query()] = None,
    sentinel_type: Annotated[SentinelType | None, Query()] = None,
    is_resolved: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AlertListResponse:
    alerts = await service.list_alerts(
        tenant_id,
        severity=severity,
        sentinel_type=sentinel_type,
        is_resolved=is_resolved,
        limit=limit,
        offset=offset,
    )
    return AlertListResponse(
        alerts=[SentinelAlertResponse.model_validate(a) for a in alerts],
        total=len(alerts),
    )


@router.get("/alerts/{alert_id}", response_model=SentinelAlertResponse)
async def get_alert(
    alert_id: UUID,
    service: Annotated[SentinelService, Depends(get_sentinel_service)],
) -> SentinelAlertResponse:
    try:
        alert = await service.get_alert(alert_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return SentinelAlertResponse.model_validate(alert)


@router.post("/alerts/{alert_id}/resolve", response_model=SentinelAlertResponse)
async def resolve_alert(
    alert_id: UUID,
    request: ResolveAlertRequest,
    service: Annotated[SentinelService, Depends(get_sentinel_service)],
) -> SentinelAlertResponse:
    try:
        alert = await service.resolve_alert(alert_id, request.action)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return SentinelAlertResponse.model_validate(alert)


@router.post(
    "/policies",
    status_code=status.HTTP_201_CREATED,
    response_model=PolicyResponse,
)
async def create_policy(
    create: PolicyCreate,
    service: Annotated[SentinelService, Depends(get_sentinel_service)],
) -> PolicyResponse:
    policy = await service.create_policy(create)
    return PolicyResponse.model_validate(policy)


@router.get("/policies", response_model=PolicyListResponse)
async def list_policies(
    tenant_id: str,
    service: Annotated[SentinelService, Depends(get_sentinel_service)],
    active_only: Annotated[bool, Query()] = True,
) -> PolicyListResponse:
    policies = await service.list_policies(tenant_id, active_only=active_only)
    return PolicyListResponse(
        policies=[PolicyResponse.model_validate(p) for p in policies],
        total=len(policies),
    )


@router.delete(
    "/policies/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def deactivate_policy(
    policy_id: UUID,
    service: Annotated[SentinelService, Depends(get_sentinel_service)],
) -> None:
    try:
        await service.deactivate_policy(policy_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found"
        )
