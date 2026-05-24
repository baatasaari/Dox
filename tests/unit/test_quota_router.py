"""Module 9 — Quota: HTTP route tests."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from common.schemas.quota import QuotaStatus
from services.quota.deps import get_quota_service
from services.quota.router import router
from services.quota.service import QuotaService


def _make_quota_status(tenant_id: str = "tenant-acme") -> QuotaStatus:
    now = datetime.now(UTC)
    return QuotaStatus(
        tenant_id=tenant_id,
        subscription_tier="starter",
        daily_limit=1_000,
        monthly_limit=20_000,
        events_today=50,
        events_this_month=200,
        daily_remaining=950,
        monthly_remaining=19_800,
        is_over_daily_limit=False,
        is_over_monthly_limit=False,
        day_window_start=now,
        month_window_start=now,
    )


def _make_mock_service() -> MagicMock:
    svc = MagicMock(spec=QuotaService)
    status = _make_quota_status()
    svc.provision = AsyncMock(
        return_value=MagicMock(
            tenant_id="t",
            subscription_tier="starter",
            daily_limit=1_000,
            monthly_limit=20_000,
            events_today=0,
            events_this_month=0,
            day_window_start=datetime.now(UTC),
            month_window_start=datetime.now(UTC),
        )
    )
    svc.get_status = AsyncMock(return_value=status)
    svc.reset_daily = AsyncMock(return_value=status)
    return svc


@pytest.fixture()
async def client() -> AsyncGenerator[tuple[AsyncClient, MagicMock], None]:
    app = FastAPI()
    app.include_router(router)
    mock_svc = _make_mock_service()

    async def override() -> QuotaService:
        return mock_svc  # type: ignore[return-value]

    app.dependency_overrides[get_quota_service] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_svc  # type: ignore[misc]


class TestProvisionEndpoint:
    async def test_returns_201(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/quota",
            json={"tenant_id": "t", "subscription_tier": "starter"},
        )
        assert r.status_code == 201

    async def test_response_has_quota_fields(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.post("/v1/quota", json={"tenant_id": "t"})
        body = r.json()
        assert "daily_limit" in body
        assert "monthly_limit" in body
        assert "events_today" in body
        assert "daily_remaining" in body

    async def test_invalid_tier_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/quota",
            json={"tenant_id": "t", "subscription_tier": "diamond"},
        )
        assert r.status_code == 422

    async def test_missing_tenant_id_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.post("/v1/quota", json={})
        assert r.status_code == 422


class TestGetStatusEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/quota/tenant-acme")
        assert r.status_code == 200

    async def test_response_shape(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/quota/tenant-acme")
        body = r.json()
        assert body["tenant_id"] == "tenant-acme"
        assert "is_over_daily_limit" in body
        assert "is_over_monthly_limit" in body
        assert "daily_remaining" in body

    async def test_calls_service_with_tenant_id(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        await ac.get("/v1/quota/my-tenant")
        mock_svc.get_status.assert_awaited_once_with("my-tenant")


class TestResetDailyEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post("/v1/quota/tenant-acme/reset-daily")
        assert r.status_code == 200

    async def test_response_shows_zero_events_today(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        reset_status = _make_quota_status()
        reset_status = reset_status.model_copy(update={"events_today": 0})
        mock_svc.reset_daily = AsyncMock(return_value=reset_status)
        r = await ac.post("/v1/quota/tenant-acme/reset-daily")
        assert r.json()["events_today"] == 0
