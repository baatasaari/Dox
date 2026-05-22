"""Pydantic schemas for compliance reports."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EventSummary(BaseModel):
    total_count: int
    by_type: dict[str, int]
    lookback_hours: int


class AlertSummary(BaseModel):
    total_count: int
    unresolved_count: int
    by_severity: dict[str, int]
    by_type: dict[str, int]


class QuotaSummary(BaseModel):
    subscription_tier: str
    daily_remaining: int
    monthly_remaining: int
    is_over_daily_limit: bool
    is_over_monthly_limit: bool


class PolicySummary(BaseModel):
    active_count: int


class ComplianceReport(BaseModel):
    tenant_id: str
    generated_at: datetime
    lookback_hours: int
    events: EventSummary
    alerts: AlertSummary
    quota: QuotaSummary
    policies: PolicySummary
