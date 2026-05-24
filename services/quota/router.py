"""Quota service HTTP routes — provisioning and status inspection."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from common.schemas.quota import QuotaProvision, QuotaStatus

from .deps import get_quota_service
from .service import QuotaService

router = APIRouter(prefix="/v1/quota", tags=["quota"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=QuotaStatus)
async def provision_quota(
    create: QuotaProvision,
    service: Annotated[QuotaService, Depends(get_quota_service)],
) -> QuotaStatus:
    quota = await service.provision(create)
    return QuotaService._to_status(quota)


@router.get("/{tenant_id}", response_model=QuotaStatus)
async def get_quota_status(
    tenant_id: str,
    service: Annotated[QuotaService, Depends(get_quota_service)],
) -> QuotaStatus:
    return await service.get_status(tenant_id)


@router.post("/{tenant_id}/reset-daily", response_model=QuotaStatus)
async def reset_daily_quota(
    tenant_id: str,
    service: Annotated[QuotaService, Depends(get_quota_service)],
) -> QuotaStatus:
    return await service.reset_daily(tenant_id)
