"""Event query service — read-only access to persisted EventRecords."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.audit.integrity import IntegrityReport, verify_tenant_integrity
from common.exceptions import NotFoundError
from common.models.event import EventRecord
from common.schemas.query import EventFilter


class EventQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_event(self, event_id: UUID) -> EventRecord:
        result = await self._session.execute(
            select(EventRecord).where(EventRecord.event_id == event_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise NotFoundError(f"Event {event_id} not found")
        return record

    async def list_events(self, filters: EventFilter) -> list[EventRecord]:
        conditions = [EventRecord.tenant_id == filters.tenant_id]
        if filters.agent_id is not None:
            conditions.append(EventRecord.agent_id == filters.agent_id)
        if filters.event_type is not None:
            conditions.append(EventRecord.event_type == filters.event_type)
        if filters.environment is not None:
            conditions.append(EventRecord.environment == filters.environment)
        if filters.session_id is not None:
            conditions.append(EventRecord.session_id == filters.session_id)
        if filters.from_ts is not None:
            conditions.append(EventRecord.timestamp >= filters.from_ts)
        if filters.to_ts is not None:
            conditions.append(EventRecord.timestamp <= filters.to_ts)

        result = await self._session.execute(
            select(EventRecord)
            .where(and_(*conditions))
            .order_by(EventRecord.timestamp.desc())
            .limit(filters.limit)
            .offset(filters.offset)
        )
        return list(result.scalars().all())

    async def count_events(self, filters: EventFilter) -> int:
        conditions = [EventRecord.tenant_id == filters.tenant_id]
        if filters.agent_id is not None:
            conditions.append(EventRecord.agent_id == filters.agent_id)
        if filters.event_type is not None:
            conditions.append(EventRecord.event_type == filters.event_type)
        if filters.environment is not None:
            conditions.append(EventRecord.environment == filters.environment)
        if filters.session_id is not None:
            conditions.append(EventRecord.session_id == filters.session_id)
        if filters.from_ts is not None:
            conditions.append(EventRecord.timestamp >= filters.from_ts)
        if filters.to_ts is not None:
            conditions.append(EventRecord.timestamp <= filters.to_ts)

        result = await self._session.execute(
            select(func.count()).select_from(EventRecord).where(and_(*conditions))
        )
        return result.scalar_one()

    async def verify_integrity(
        self, tenant_id: str, limit: int = 1000
    ) -> IntegrityReport:
        result = await self._session.execute(
            select(EventRecord)
            .where(EventRecord.tenant_id == tenant_id)
            .order_by(EventRecord.timestamp.asc())
            .limit(limit)
        )
        records = list(result.scalars().all())
        return verify_tenant_integrity(records)
