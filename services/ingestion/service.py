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
        sentinel_service: object | None = None,
        quota_service: object | None = None,
    ) -> None:
        self._session = session
        self._event_bus = event_bus
        self._metrics = metrics
        self._sentinel = sentinel_service
        self._quota = quota_service

    async def ingest(self, event: CanonicalEvent) -> EventRecord:
        await self._check_quota(event.tenant_id)
        record = EventRecord.from_canonical(event)
        self._session.add(record)
        await self._session.commit()
        await self._event_bus.publish(_INGESTED_TOPIC, event.model_dump(mode="json"))
        self._metrics.increment("events.ingested", tags={"event_type": event.event_type})
        await self._run_sentinel(event)
        return record

    async def ingest_batch(self, events: list[CanonicalEvent]) -> list[EventRecord]:
        if not events:
            return []
        for event in events:
            await self._check_quota(event.tenant_id)
        records = [EventRecord.from_canonical(e) for e in events]
        for record in records:
            self._session.add(record)
        await self._session.commit()
        for event in events:
            await self._event_bus.publish(_INGESTED_TOPIC, event.model_dump(mode="json"))
        self._metrics.increment("events.ingested_batch", value=len(events))
        for event in events:
            await self._run_sentinel(event)
        return records

    async def _check_quota(self, tenant_id: str) -> None:
        if self._quota is None:
            return
        from services.quota.service import QuotaService

        quota: QuotaService = self._quota  # type: ignore[assignment]
        await quota.check_and_increment(tenant_id)

    async def _run_sentinel(self, event: CanonicalEvent) -> None:
        if self._sentinel is None:
            return
        from services.sentinel.service import SentinelService

        sentinel: SentinelService = self._sentinel  # type: ignore[assignment]
        alert_creates = SentinelService.evaluate_event(event)
        for create in alert_creates:
            await sentinel.create_alert(create)
