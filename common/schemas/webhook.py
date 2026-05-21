"""Pydantic schemas for webhook management and delivery."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class WebhookCreate(BaseModel):
    tenant_id: str
    url: str
    secret: str = Field(min_length=16)
    event_types: list[str] = Field(default_factory=lambda: ["*"])
    description: str = ""

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("url must start with http:// or https://")
        return v


class WebhookResponse(BaseModel):
    id: UUID
    tenant_id: str
    url: str
    event_types: list[str]
    description: str
    is_active: bool
    failure_count: int
    last_delivered_at: datetime | None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class WebhookListResponse(BaseModel):
    webhooks: list[WebhookResponse]
    total: int


class DispatchRequest(BaseModel):
    tenant_id: str
    sentinel_type: str
    payload: dict[str, Any]


class WebhookDeliveryResult(BaseModel):
    webhook_id: UUID
    url: str
    success: bool
    status_code: int | None
    error: str | None
    delivered_at: datetime


class DispatchResult(BaseModel):
    deliveries: list[WebhookDeliveryResult]
    successful: int
    failed: int
