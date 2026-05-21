"""Module 7 — Drift: HTTP route tests."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from common.exceptions import NotFoundError
from common.models.baseline import AgentBaseline
from common.schemas.drift import DriftReportResponse, DriftScore
from services.drift.deps import get_drift_service
from services.drift.router import router
from services.drift.service import DriftDetectionService


def _make_baseline(agent_id: str = "agent-1") -> AgentBaseline:
    return AgentBaseline(
        id=uuid4(),
        tenant_id="tenant-acme",
        agent_id=agent_id,
        lookback_hours=24,
        event_counts={"agent_started": 10},
        total_events=10,
        computed_at=datetime.now(UTC),
    )


def _make_mock_service() -> MagicMock:
    svc = MagicMock(spec=DriftDetectionService)
    b = _make_baseline()
    svc.compute_baseline = AsyncMock(return_value=b)
    svc.list_baselines = AsyncMock(return_value=[b])
    svc.get_baseline = AsyncMock(return_value=b)
    svc.deactivate_baseline = AsyncMock(return_value=b)
    svc.analyze = AsyncMock(
        return_value=DriftReportResponse(
            drift_score=DriftScore(
                tenant_id="tenant-acme",
                agent_id="agent-1",
                score=0.1,
                severity="none",
                recent_event_count=5,
                baseline_total_events=10,
                deviations=[],
            ),
            baseline_id=b.id,
            alert_created=False,
        )
    )
    return svc


@pytest.fixture()
async def client() -> AsyncGenerator[tuple[AsyncClient, MagicMock], None]:
    app = FastAPI()
    app.include_router(router)
    mock_svc = _make_mock_service()

    async def override() -> DriftDetectionService:
        return mock_svc  # type: ignore[return-value]

    app.dependency_overrides[get_drift_service] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_svc  # type: ignore[misc]


class TestComputeBaselineEndpoint:
    async def test_returns_201(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/drift/baselines",
            json={"tenant_id": "t", "agent_id": "a", "lookback_hours": 24},
        )
        assert r.status_code == 201

    async def test_response_shape(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/drift/baselines",
            json={"tenant_id": "t", "agent_id": "a"},
        )
        body = r.json()
        assert "id" in body
        assert "event_counts" in body
        assert "total_events" in body
        assert "is_active" in body

    async def test_missing_tenant_id_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.post("/v1/drift/baselines", json={"agent_id": "a"})
        assert r.status_code == 422

    async def test_lookback_hours_below_minimum_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/drift/baselines",
            json={"tenant_id": "t", "agent_id": "a", "lookback_hours": 0},
        )
        assert r.status_code == 422


class TestListBaselinesEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/drift/baselines", params={"tenant_id": "tenant-acme"})
        assert r.status_code == 200

    async def test_response_has_baselines_and_total(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get("/v1/drift/baselines", params={"tenant_id": "tenant-acme"})
        body = r.json()
        assert "baselines" in body
        assert "total" in body

    async def test_missing_tenant_id_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get("/v1/drift/baselines")
        assert r.status_code == 422

    async def test_total_matches_list_length(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        baselines = [_make_baseline() for _ in range(3)]
        mock_svc.list_baselines = AsyncMock(return_value=baselines)
        r = await ac.get("/v1/drift/baselines", params={"tenant_id": "t"})
        body = r.json()
        assert body["total"] == 3
        assert len(body["baselines"]) == 3


class TestGetBaselineEndpoint:
    async def test_returns_200_for_existing(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get(f"/v1/drift/baselines/{uuid4()}")
        assert r.status_code == 200

    async def test_returns_404_when_missing(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.get_baseline = AsyncMock(side_effect=NotFoundError("not found"))
        r = await ac.get(f"/v1/drift/baselines/{uuid4()}")
        assert r.status_code == 404

    async def test_invalid_uuid_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get("/v1/drift/baselines/not-a-uuid")
        assert r.status_code == 422


class TestDeactivateBaselineEndpoint:
    async def test_returns_204(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.delete(f"/v1/drift/baselines/{uuid4()}")
        assert r.status_code == 204

    async def test_returns_404_when_missing(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.deactivate_baseline = AsyncMock(side_effect=NotFoundError("gone"))
        r = await ac.delete(f"/v1/drift/baselines/{uuid4()}")
        assert r.status_code == 404


class TestAnalyzeEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/drift/analyze",
            json={"tenant_id": "t", "agent_id": "a", "lookback_hours": 1},
        )
        assert r.status_code == 200

    async def test_response_shape(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/drift/analyze",
            json={"tenant_id": "t", "agent_id": "a"},
        )
        body = r.json()
        assert "drift_score" in body
        assert "baseline_id" in body
        assert "alert_created" in body

    async def test_drift_score_fields_present(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/drift/analyze",
            json={"tenant_id": "t", "agent_id": "a"},
        )
        score = r.json()["drift_score"]
        assert "score" in score
        assert "severity" in score
        assert "deviations" in score

    async def test_missing_tenant_id_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.post("/v1/drift/analyze", json={"agent_id": "a"})
        assert r.status_code == 422

    async def test_lookback_hours_above_maximum_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/drift/analyze",
            json={"tenant_id": "t", "agent_id": "a", "lookback_hours": 999},
        )
        assert r.status_code == 422
