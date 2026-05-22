"""Compliance reporting HTTP routes."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from common.schemas.compliance import ComplianceReport

from .deps import get_compliance_service
from .service import ComplianceService

router = APIRouter(prefix="/v1/compliance", tags=["compliance"])


@router.get("/{tenant_id}", response_model=ComplianceReport)
async def get_compliance_report(
    tenant_id: str,
    service: Annotated[ComplianceService, Depends(get_compliance_service)],
    lookback_hours: Annotated[int, Query(ge=1, le=8760)] = 24,
) -> ComplianceReport:
    return await service.generate_report(tenant_id, lookback_hours=lookback_hours)
