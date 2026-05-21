"""Ingestion service — persists and publishes CanonicalEvents."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from common.adapters.base import EventBusAdapter, MetricsAdapter
from common.models.event import EventRecord
from common.schemas.events import CanonicalEvent

_INGESTED_TOPIC = "dox.events.ingested"


class IngestionService:
    def __init__(
        self,
        session: AsyncSession,
        event_bus: EventBusAdapter,
        metrics: MetricsAdapter,
    ) -> None:
        self._session = session
        self._event_bus = event_bus
        self._metrics = metrics

    async def ingest(self, event: CanonicalEvent) -> EventRecord:
        record = EventRecord.from_canonical(event)
        self._session.add(record)
        await self._session.commit()
        await self._event_bus.publish(_INGESTED_TOPIC, event.model_dump(mode="json"))
        self._metrics.increment("events.ingested", tags={"event_type": event.event_type})
        return record

    async def ingest_batch(self, events: list[CanonicalEvent]) -> list[EventRecord]:
        if not events:
            return []
        records = [EventRecord.from_canonical(e) for e in events]
        for record in records:
            self._session.add(record)
        await self._session.commit()
        for event in events:
            await self._event_bus.publish(_INGESTED_TOPIC, event.model_dump(mode="json"))
        self._metrics.increment("events.ingested_batch", value=len(events))
        return records
