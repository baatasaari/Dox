"""Pydantic schemas for quota provisioning and status."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from common.schemas.enums import SubscriptionTier


class QuotaProvision(BaseModel):
    tenant_id: str
    subscription_tier: SubscriptionTier = SubscriptionTier.starter


class QuotaStatus(BaseModel):
    tenant_id: str
    subscription_tier: str
    daily_limit: int
    monthly_limit: int
    events_today: int
    events_this_month: int
    daily_remaining: int
    monthly_remaining: int
    is_over_daily_limit: bool
    is_over_monthly_limit: bool
    day_window_start: datetime
    month_window_start: datetime

    model_config = {"from_attributes": True}
