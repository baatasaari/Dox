"""Audit trail HTTP routes — record and query governance actions."""
from __future__ import annotations

import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from common.exceptions import NotFoundError
from common.schemas.audit_log import AuditEntryCreate, AuditEntryResponse, AuditListResponse

from .deps import get_audit_service
from .service import AuditService

router = APIRouter(prefix="/v1/audit-log", tags=["audit-log"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AuditEntryResponse)
async def record_entry(
    create: AuditEntryCreate,
    service: Annotated[AuditService, Depends(get_audit_service)],
) -> AuditEntryResponse:
    entry = await service.record(create)
    return AuditEntryResponse.model_validate(entry)


@router.get("/{tenant_id}", response_model=AuditListResponse)
async def list_entries(
    tenant_id: str,
    service: Annotated[AuditService, Depends(get_audit_service)],
    action: Annotated[str | None, Query()] = None,
    resource_type: Annotated[str | None, Query()] = None,
    actor_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditListResponse:
    entries, total = await asyncio.gather(
        service.list_for_tenant(
            tenant_id,
            action=action,
            resource_type=resource_type,
            actor_id=actor_id,
            limit=limit,
            offset=offset,
        ),
        service.count_for_tenant(
            tenant_id,
            action=action,
            resource_type=resource_type,
            actor_id=actor_id,
        ),
    )
    return AuditListResponse(
        entries=[AuditEntryResponse.model_validate(e) for e in entries],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{tenant_id}/{entry_id}", response_model=AuditEntryResponse)
async def get_entry(
    tenant_id: str,
    entry_id: UUID,
    service: Annotated[AuditService, Depends(get_audit_service)],
) -> AuditEntryResponse:
    try:
        entry = await service.get(entry_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit entry not found")
    if entry.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit entry not found")
    return AuditEntryResponse.model_validate(entry)
