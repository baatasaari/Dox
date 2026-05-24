"""Tenant management HTTP routes."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from common.exceptions import ConflictError, NotFoundError
from common.schemas.tenant import (
    TenantCreate,
    TenantListResponse,
    TenantResponse,
    TenantUpdate,
)

from .deps import get_tenant_service
from .service import TenantService

router = APIRouter(prefix="/v1/tenants", tags=["tenants"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TenantResponse)
async def create_tenant(
    create: TenantCreate,
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> TenantResponse:
    try:
        tenant = await service.create(create)
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail)
    return TenantResponse.model_validate(tenant)


@router.get("", response_model=TenantListResponse)
async def list_tenants(
    service: Annotated[TenantService, Depends(get_tenant_service)],
    active_only: Annotated[bool, Query()] = True,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TenantListResponse:
    tenants = await service.list_tenants(active_only=active_only, limit=limit, offset=offset)
    return TenantListResponse(
        tenants=[TenantResponse.model_validate(t) for t in tenants],
        total=len(tenants),
    )


@router.get("/by-slug/{slug}", response_model=TenantResponse)
async def get_tenant_by_slug(
    slug: str,
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> TenantResponse:
    try:
        tenant = await service.get_by_slug(slug)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantResponse.model_validate(tenant)


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: UUID,
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> TenantResponse:
    try:
        tenant = await service.get(tenant_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantResponse.model_validate(tenant)


@router.put("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: UUID,
    update: TenantUpdate,
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> TenantResponse:
    try:
        tenant = await service.update(tenant_id, update)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantResponse.model_validate(tenant)


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def deactivate_tenant(
    tenant_id: UUID,
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> None:
    try:
        await service.deactivate(tenant_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")


@router.post("/{tenant_id}/activate", response_model=TenantResponse)
async def activate_tenant(
    tenant_id: UUID,
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> TenantResponse:
    try:
        tenant = await service.activate(tenant_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantResponse.model_validate(tenant)
