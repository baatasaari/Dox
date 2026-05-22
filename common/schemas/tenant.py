"""Pydantic schemas for tenant management."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from common.schemas.enums import SubscriptionTier


class TenantCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    subscription_tier: SubscriptionTier = SubscriptionTier.starter


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    subscription_tier: SubscriptionTier | None = None
    is_active: bool | None = None


class TenantResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    subscription_tier: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TenantListResponse(BaseModel):
    tenants: list[TenantResponse]
    total: int
