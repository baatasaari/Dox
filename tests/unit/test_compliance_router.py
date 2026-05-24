"""Module 13 — Compliance Reporting: HTTP route tests."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from common.schemas.compliance import (
    AlertSummary,
    ComplianceReport,
    EventSummary,
    PolicySummary,
    QuotaSummary,
)
from services.compliance.deps import get_compliance_service
from services.compliance.router import router
from services.compliance.service import ComplianceService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_report(tenant_id: str = "acme", lookback_hours: int = 24) -> ComplianceReport:
    now = datetime.now(UTC)
    return ComplianceReport(
        tenant_id=tenant_id,
        generated_at=now,
        lookback_hours=lookback_hours,
        events=EventSummary(total_count=10, by_type={"agent_started": 10}, lookback_hours=24),
        alerts=AlertSummary(
            total_count=2,
            unresolved_count=1,
            by_severity={"high": 2},
            by_type={"tool_misuse": 2},
        ),
        quota=QuotaSummary(
            subscription_tier="starter",
            daily_remaining=900,
            monthly_remaining=18000,
            is_over_daily_limit=False,
            is_over_monthly_limit=False,
        ),
        policies=PolicySummary(active_count=3),
    )


def _make_mock_service() -> MagicMock:
    svc = MagicMock(spec=ComplianceService)
    svc.generate_report = AsyncMock(return_value=_make_report())
    return svc


@pytest.fixture()
async def client() -> AsyncGenerator[tuple[AsyncClient, MagicMock], None]:
    app = FastAPI()
    app.include_router(router)
    mock_svc = _make_mock_service()

    async def override() -> ComplianceService:
        return mock_svc  # type: ignore[return-value]

    app.dependency_overrides[get_compliance_service] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_svc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# GET /v1/compliance/{tenant_id}
# ---------------------------------------------------------------------------


class TestGetComplianceReport:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/compliance/acme")
        assert r.status_code == 200

    async def test_response_has_all_sections(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get("/v1/compliance/acme")
        body = r.json()
        assert "tenant_id" in body
        assert "generated_at" in body
        assert "lookback_hours" in body
        assert "events" in body
        assert "alerts" in body
        assert "quota" in body
        assert "policies" in body

    async def test_events_section_shape(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/compliance/acme")
        ev = r.json()["events"]
        assert "total_count" in ev
        assert "by_type" in ev
        assert "lookback_hours" in ev

    async def test_alerts_section_shape(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/compliance/acme")
        al = r.json()["alerts"]
        assert "total_count" in al
        assert "unresolved_count" in al
        assert "by_severity" in al
        assert "by_type" in al

    async def test_quota_section_shape(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/compliance/acme")
        q = r.json()["quota"]
        assert "subscription_tier" in q
        assert "daily_remaining" in q
        assert "is_over_daily_limit" in q

    async def test_default_lookback_is_24(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, mock_svc = client
        await ac.get("/v1/compliance/acme")
        mock_svc.generate_report.assert_awaited_once_with("acme", lookback_hours=24)

    async def test_custom_lookback_hours_forwarded(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        await ac.get("/v1/compliance/acme?lookback_hours=72")
        mock_svc.generate_report.assert_awaited_once_with("acme", lookback_hours=72)

    async def test_lookback_zero_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get("/v1/compliance/acme?lookback_hours=0")
        assert r.status_code == 422

    async def test_tenant_id_forwarded_to_service(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.generate_report = AsyncMock(return_value=_make_report("my-tenant"))
        await ac.get("/v1/compliance/my-tenant")
        call_args = mock_svc.generate_report.call_args
        assert call_args[0][0] == "my-tenant"

    async def test_report_tenant_id_in_response(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.generate_report = AsyncMock(return_value=_make_report("beta-corp"))
        r = await ac.get("/v1/compliance/beta-corp")
        assert r.json()["tenant_id"] == "beta-corp"
