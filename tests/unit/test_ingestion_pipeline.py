"""Module 6 — Sentinel pipeline integration tests for IngestionService."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from common.adapters.event_bus import InMemoryEventBusAdapter
from common.adapters.metrics import InMemoryMetricsAdapter
from common.schemas.enums import EventType
from common.schemas.events import CanonicalEvent
from services.ingestion.service import IngestionService


def _make_event(event_type: str = "agent_started") -> CanonicalEvent:
    now = datetime.now(UTC)
    return CanonicalEvent(
        event_id=uuid4(),
        trace_id=uuid4(),
        session_id="sess-1",
        tenant_id="tenant-acme",
        agent_id="agent-1",
        agent_version="1.0.0",
        event_type=event_type,
        environment="dev",
        timestamp=now,
        client_timestamp=now,
        correlation_id="corr-1",
        payload={"step": "test"},
    )


def _make_service(sentinel: object = None) -> tuple[IngestionService, MagicMock]:
    session = MagicMock()
    session.commit = AsyncMock()
    event_bus = InMemoryEventBusAdapter()
    metrics = InMemoryMetricsAdapter()
    svc = IngestionService(
        session=session,  # type: ignore[arg-type]
        event_bus=event_bus,
        metrics=metrics,
        sentinel_service=sentinel,
    )
    return svc, session


class TestSentinelPipeline:
    async def test_no_sentinel_ingest_completes_normally(self) -> None:
        svc, _ = _make_service()
        event = _make_event(EventType.tool_call_blocked)
        record = await svc.ingest(event)
        assert record.event_id == event.event_id

    async def test_triggering_event_calls_create_alert(self) -> None:
        mock_sentinel = MagicMock()
        mock_sentinel.create_alert = AsyncMock()
        svc, _ = _make_service(sentinel=mock_sentinel)
        event = _make_event(EventType.tool_call_blocked)
        await svc.ingest(event)
        mock_sentinel.create_alert.assert_awaited_once()

    async def test_non_triggering_event_does_not_create_alert(self) -> None:
        mock_sentinel = MagicMock()
        mock_sentinel.create_alert = AsyncMock()
        svc, _ = _make_service(sentinel=mock_sentinel)
        event = _make_event(EventType.agent_started)
        await svc.ingest(event)
        mock_sentinel.create_alert.assert_not_awaited()

    async def test_agent_terminated_creates_critical_alert(self) -> None:
        from common.schemas.enums import Severity

        mock_sentinel = MagicMock()
        created_alerts = []

        async def capture(create: object) -> object:
            created_alerts.append(create)
            return MagicMock()

        mock_sentinel.create_alert = capture
        svc, _ = _make_service(sentinel=mock_sentinel)
        event = _make_event(EventType.agent_terminated)
        await svc.ingest(event)
        assert len(created_alerts) == 1
        assert created_alerts[0].severity == Severity.critical

    async def test_batch_ingest_triggers_sentinel_per_event(self) -> None:
        mock_sentinel = MagicMock()
        mock_sentinel.create_alert = AsyncMock()
        svc, _ = _make_service(sentinel=mock_sentinel)
        events = [_make_event(EventType.tool_call_blocked) for _ in range(3)]
        await svc.ingest_batch(events)
        assert mock_sentinel.create_alert.await_count == 3

    async def test_batch_with_mixed_events_only_triggers_on_matching(self) -> None:
        mock_sentinel = MagicMock()
        mock_sentinel.create_alert = AsyncMock()
        svc, _ = _make_service(sentinel=mock_sentinel)
        events = [
            _make_event(EventType.agent_started),
            _make_event(EventType.tool_call_blocked),
            _make_event(EventType.agent_started),
        ]
        await svc.ingest_batch(events)
        assert mock_sentinel.create_alert.await_count == 1

    async def test_sentinel_alert_matches_event_tenant(self) -> None:
        from common.schemas.sentinel import SentinelAlertCreate

        mock_sentinel = MagicMock()
        captured: list[SentinelAlertCreate] = []

        async def capture(create: SentinelAlertCreate) -> object:
            captured.append(create)
            return MagicMock()

        mock_sentinel.create_alert = capture
        svc, _ = _make_service(sentinel=mock_sentinel)
        event = _make_event(EventType.policy_failed)
        await svc.ingest(event)
        assert len(captured) == 1
        assert captured[0].tenant_id == event.tenant_id
        assert captured[0].agent_id == event.agent_id
