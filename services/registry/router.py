"""Agent Registry HTTP routes."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from common.exceptions import ConflictError, NotFoundError
from common.schemas.agent import (
    AgentProfileCreate,
    AgentProfileListResponse,
    AgentProfileResponse,
    AgentProfileUpdate,
    HeartbeatResponse,
)

from .deps import get_registry_service
from .service import AgentRegistryService

router = APIRouter(prefix="/v1/agents", tags=["registry"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AgentProfileResponse)
async def register_agent(
    create: AgentProfileCreate,
    service: Annotated[AgentRegistryService, Depends(get_registry_service)],
) -> AgentProfileResponse:
    try:
        profile = await service.create(create)
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail)
    return AgentProfileResponse.model_validate(profile)


@router.get("", response_model=AgentProfileListResponse)
async def list_agents(
    tenant_id: str,
    service: Annotated[AgentRegistryService, Depends(get_registry_service)],
    active_only: Annotated[bool, Query()] = True,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AgentProfileListResponse:
    profiles = await service.list_for_tenant(
        tenant_id, active_only=active_only, limit=limit, offset=offset
    )
    return AgentProfileListResponse(
        agents=[AgentProfileResponse.model_validate(p) for p in profiles],
        total=len(profiles),
    )


@router.get("/{profile_id}", response_model=AgentProfileResponse)
async def get_agent(
    profile_id: UUID,
    service: Annotated[AgentRegistryService, Depends(get_registry_service)],
) -> AgentProfileResponse:
    try:
        profile = await service.get(profile_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return AgentProfileResponse.model_validate(profile)


@router.put("/{profile_id}", response_model=AgentProfileResponse)
async def update_agent(
    profile_id: UUID,
    update: AgentProfileUpdate,
    service: Annotated[AgentRegistryService, Depends(get_registry_service)],
) -> AgentProfileResponse:
    try:
        profile = await service.update(profile_id, update)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return AgentProfileResponse.model_validate(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def deactivate_agent(
    profile_id: UUID,
    service: Annotated[AgentRegistryService, Depends(get_registry_service)],
) -> None:
    try:
        await service.delete(profile_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")


@router.post("/{tenant_id}/{agent_id}/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    tenant_id: str,
    agent_id: str,
    service: Annotated[AgentRegistryService, Depends(get_registry_service)],
) -> HeartbeatResponse:
    try:
        profile = await service.heartbeat(tenant_id, agent_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return HeartbeatResponse(
        agent_id=profile.agent_id,
        last_seen_at=profile.last_seen_at,
    )
