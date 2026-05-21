"""Module 9 — Quota enforcement integration in IngestionService."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common.adapters.event_bus import InMemoryEventBusAdapter
from common.adapters.metrics import InMemoryMetricsAdapter
from common.exceptions import QuotaExceededError
from common.schemas.events import CanonicalEvent
from services.ingestion.service import IngestionService


def _make_event() -> CanonicalEvent:
    now = datetime.now(UTC)
    return CanonicalEvent(
        event_id=uuid4(),
        trace_id=uuid4(),
        session_id="sess-1",
        tenant_id="tenant-acme",
        agent_id="agent-1",
        agent_version="1.0.0",
        event_type="agent_started",
        environment="dev",
        timestamp=now,
        client_timestamp=now,
        correlation_id="corr-1",
        payload={"step": "init"},
    )


def _make_service(quota: object = None) -> tuple[IngestionService, MagicMock]:
    session = MagicMock()
    session.commit = AsyncMock()
    svc = IngestionService(
        session=session,  # type: ignore[arg-type]
        event_bus=InMemoryEventBusAdapter(),
        metrics=InMemoryMetricsAdapter(),
        quota_service=quota,
    )
    return svc, session


class TestQuotaEnforcement:
    async def test_no_quota_service_ingest_succeeds(self) -> None:
        svc, _ = _make_service()
        record = await svc.ingest(_make_event())
        assert record is not None

    async def test_quota_check_called_on_ingest(self) -> None:
        mock_quota = MagicMock()
        mock_quota.check_and_increment = AsyncMock()
        svc, _ = _make_service(quota=mock_quota)
        await svc.ingest(_make_event())
        mock_quota.check_and_increment.assert_awaited_once_with("tenant-acme")

    async def test_quota_exceeded_blocks_ingest(self) -> None:
        mock_quota = MagicMock()
        mock_quota.check_and_increment = AsyncMock(
            side_effect=QuotaExceededError("limit reached")
        )
        svc, session = _make_service(quota=mock_quota)
        with pytest.raises(QuotaExceededError):
            await svc.ingest(_make_event())
        session.add.assert_not_called()

    async def test_quota_checked_per_event_in_batch(self) -> None:
        mock_quota = MagicMock()
        mock_quota.check_and_increment = AsyncMock()
        svc, _ = _make_service(quota=mock_quota)
        events = [_make_event() for _ in range(3)]
        await svc.ingest_batch(events)
        assert mock_quota.check_and_increment.await_count == 3

    async def test_quota_exceeded_in_batch_blocks_all(self) -> None:
        mock_quota = MagicMock()
        mock_quota.check_and_increment = AsyncMock(
            side_effect=QuotaExceededError("limit reached")
        )
        svc, session = _make_service(quota=mock_quota)
        events = [_make_event() for _ in range(3)]
        with pytest.raises(QuotaExceededError):
            await svc.ingest_batch(events)
        session.add.assert_not_called()
