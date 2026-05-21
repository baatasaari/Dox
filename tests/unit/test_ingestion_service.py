"""Module 3 — Ingestion: service layer tests."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common.adapters.event_bus import InMemoryEventBusAdapter
from common.adapters.metrics import InMemoryMetricsAdapter
from common.schemas.events import CanonicalEvent
from services.ingestion.service import IngestionService


@pytest.fixture()
def mock_session() -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock(return_value=None)
    return session


@pytest.fixture()
def event_bus() -> InMemoryEventBusAdapter:
    return InMemoryEventBusAdapter()


@pytest.fixture()
def metrics() -> InMemoryMetricsAdapter:
    return InMemoryMetricsAdapter()


@pytest.fixture()
def service(
    mock_session: MagicMock,
    event_bus: InMemoryEventBusAdapter,
    metrics: InMemoryMetricsAdapter,
) -> IngestionService:
    return IngestionService(mock_session, event_bus, metrics)  # type: ignore[arg-type]


@pytest.fixture()
def canonical() -> CanonicalEvent:
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


class TestIngestionServiceIngest:
    async def test_ingest_calls_session_add(
        self, service: IngestionService, mock_session: MagicMock, canonical: CanonicalEvent
    ) -> None:
        await service.ingest(canonical)
        mock_session.add.assert_called_once()

    async def test_ingest_calls_session_commit(
        self, service: IngestionService, mock_session: MagicMock, canonical: CanonicalEvent
    ) -> None:
        await service.ingest(canonical)
        mock_session.commit.assert_awaited_once()

    async def test_ingest_publishes_to_event_bus(
        self,
        service: IngestionService,
        event_bus: InMemoryEventBusAdapter,
        canonical: CanonicalEvent,
    ) -> None:
        await service.ingest(canonical)
        events = event_bus.get_events("dox.events.ingested")
        assert len(events) == 1

    async def test_published_event_contains_correct_event_id(
        self,
        service: IngestionService,
        event_bus: InMemoryEventBusAdapter,
        canonical: CanonicalEvent,
    ) -> None:
        await service.ingest(canonical)
        published = event_bus.get_events("dox.events.ingested")[0]
        assert published["event_id"] == str(canonical.event_id)

    async def test_ingest_increments_metrics(
        self,
        service: IngestionService,
        metrics: InMemoryMetricsAdapter,
        canonical: CanonicalEvent,
    ) -> None:
        await service.ingest(canonical)
        assert metrics.get_counter("events.ingested") == 1

    async def test_ingest_returns_event_record_with_correct_ids(
        self, service: IngestionService, canonical: CanonicalEvent
    ) -> None:
        record = await service.ingest(canonical)
        assert record.event_id == canonical.event_id
        assert record.tenant_id == canonical.tenant_id

    async def test_ingest_computes_hash_when_not_provided(
        self, service: IngestionService, canonical: CanonicalEvent
    ) -> None:
        assert canonical.payload_hash is None
        record = await service.ingest(canonical)
        assert record.payload_hash is not None
        assert len(record.payload_hash) == 64

    async def test_ingest_preserves_provided_hash(
        self, service: IngestionService, canonical: CanonicalEvent
    ) -> None:
        provided_hash = "b" * 64
        event_with_hash = canonical.model_copy(update={"payload_hash": provided_hash})
        record = await service.ingest(event_with_hash)
        assert record.payload_hash == provided_hash


class TestIngestionServiceBatch:
    async def test_ingest_batch_saves_all_records(
        self, service: IngestionService, mock_session: MagicMock, canonical: CanonicalEvent
    ) -> None:
        events = [canonical.model_copy(update={"event_id": uuid4()}) for _ in range(3)]
        await service.ingest_batch(events)
        assert mock_session.add.call_count == 3

    async def test_ingest_batch_publishes_per_event(
        self,
        service: IngestionService,
        event_bus: InMemoryEventBusAdapter,
        canonical: CanonicalEvent,
    ) -> None:
        events = [canonical.model_copy(update={"event_id": uuid4()}) for _ in range(4)]
        await service.ingest_batch(events)
        assert len(event_bus.get_events("dox.events.ingested")) == 4

    async def test_ingest_batch_increments_batch_counter(
        self,
        service: IngestionService,
        metrics: InMemoryMetricsAdapter,
        canonical: CanonicalEvent,
    ) -> None:
        events = [canonical.model_copy(update={"event_id": uuid4()}) for _ in range(5)]
        await service.ingest_batch(events)
        assert metrics.get_counter("events.ingested_batch") == 5

    async def test_ingest_batch_empty_list_returns_empty(
        self, service: IngestionService, mock_session: MagicMock
    ) -> None:
        result = await service.ingest_batch([])
        assert result == []
        mock_session.add.assert_not_called()

    async def test_ingest_batch_commits_once(
        self, service: IngestionService, mock_session: MagicMock, canonical: CanonicalEvent
    ) -> None:
        events = [canonical.model_copy(update={"event_id": uuid4()}) for _ in range(3)]
        await service.ingest_batch(events)
        mock_session.commit.assert_awaited_once()
