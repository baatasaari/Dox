"""User management HTTP routes."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from common.exceptions import ConflictError, NotFoundError
from common.schemas.user import (
    ChangePasswordRequest,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)

from .deps import get_user_service
from .service import UserService

router = APIRouter(prefix="/v1/users", tags=["users"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def create_user(
    create: UserCreate,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    try:
        user = await service.create(create)
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail)
    return UserResponse.model_validate(user)


@router.get("", response_model=UserListResponse)
async def list_users(
    tenant_id: str,
    service: Annotated[UserService, Depends(get_user_service)],
    active_only: Annotated[bool, Query()] = True,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserListResponse:
    users = await service.list_for_tenant(
        tenant_id, active_only=active_only, limit=limit, offset=offset
    )
    return UserListResponse(
        users=[UserResponse.model_validate(u) for u in users],
        total=len(users),
    )


@router.get("/by-email/{email:path}", response_model=UserResponse)
async def get_user_by_email(
    email: str,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    try:
        user = await service.get_by_email(email)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    try:
        user = await service.get(user_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    update: UserUpdate,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    try:
        user = await service.update(user_id, update)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def deactivate_user(
    user_id: UUID,
    service: Annotated[UserService, Depends(get_user_service)],
) -> None:
    try:
        await service.deactivate(user_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


@router.post("/{user_id}/change-password", response_model=UserResponse)
async def change_password(
    user_id: UUID,
    request: ChangePasswordRequest,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    try:
        user = await service.change_password(user_id, request.new_password)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)
