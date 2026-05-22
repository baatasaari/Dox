"""Pydantic schemas for user management."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from common.schemas.enums import UserRole


class UserCreate(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8)
    tenant_id: str
    role: UserRole = UserRole.viewer


class UserUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None


class ChangePasswordRequest(BaseModel):
    new_password: str = Field(min_length=8)


class UserResponse(BaseModel):
    id: UUID
    email: str
    tenant_id: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int
