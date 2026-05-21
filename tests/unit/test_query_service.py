"""Module 6 — Query service tests."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common.exceptions import NotFoundError
from common.models.event import EventRecord
from common.schemas.enums import Environment, EventType
from common.schemas.query import EventFilter
from common.schemas.validators import compute_payload_hash
from services.query.service import EventQueryService


def _make_session_scalar(obj: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    result.scalar_one.return_value = obj
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


def _make_session_scalars(items: list[object], count: int = 0) -> MagicMock:
    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = items

    count_result = MagicMock()
    count_result.scalar_one.return_value = count or len(items)

    session = MagicMock()
    session.execute = AsyncMock(side_effect=[list_result, count_result])
    return session


def _make_record(tenant_id: str = "tenant-acme") -> EventRecord:
    p = {"step": "test"}
    return EventRecord(
        id=uuid4(),
        event_id=uuid4(),
        trace_id=uuid4(),
        session_id="sess-1",
        tenant_id=tenant_id,
        agent_id="agent-1",
        agent_version="1.0.0",
        event_type="agent_started",
        environment="dev",
        timestamp=datetime.now(UTC),
        client_timestamp=datetime.now(UTC),
        schema_version="1.0",
        payload=p,
        raw_event={},
        payload_hash=compute_payload_hash(p),
    )


class TestGetEvent:
    async def test_returns_record_when_found(self) -> None:
        record = _make_record()
        session = _make_session_scalar(record)
        service = EventQueryService(session)  # type: ignore[arg-type]
        result = await service.get_event(record.event_id)
        assert result is record

    async def test_raises_not_found_when_missing(self) -> None:
        session = _make_session_scalar(None)
        service = EventQueryService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await service.get_event(uuid4())

    async def test_queries_session(self) -> None:
        record = _make_record()
        session = _make_session_scalar(record)
        service = EventQueryService(session)  # type: ignore[arg-type]
        await service.get_event(record.event_id)
        session.execute.assert_awaited_once()


class TestListEvents:
    async def test_returns_list(self) -> None:
        records = [_make_record(), _make_record()]
        session = _make_session_scalars(records)
        service = EventQueryService(session)  # type: ignore[arg-type]
        filters = EventFilter(tenant_id="tenant-acme")
        result = await service.list_events(filters)
        assert len(result) == 2

    async def test_empty_list_returned_for_no_matches(self) -> None:
        session = _make_session_scalars([])
        service = EventQueryService(session)  # type: ignore[arg-type]
        result = await service.list_events(EventFilter(tenant_id="unknown"))
        assert result == []

    async def test_filters_applied_queries_session(self) -> None:
        session = _make_session_scalars([])
        service = EventQueryService(session)  # type: ignore[arg-type]
        filters = EventFilter(
            tenant_id="t",
            agent_id="agent-1",
            event_type=EventType.agent_started,
            environment=Environment.dev,
        )
        await service.list_events(filters)
        session.execute.assert_awaited_once()


class TestCountEvents:
    async def test_returns_correct_count(self) -> None:
        result = MagicMock()
        result.scalar_one.return_value = 42
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        service = EventQueryService(session)  # type: ignore[arg-type]
        count = await service.count_events(EventFilter(tenant_id="t"))
        assert count == 42

    async def test_zero_for_no_matches(self) -> None:
        result = MagicMock()
        result.scalar_one.return_value = 0
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        service = EventQueryService(session)  # type: ignore[arg-type]
        count = await service.count_events(EventFilter(tenant_id="unknown"))
        assert count == 0


class TestVerifyIntegrity:
    async def test_returns_integrity_report(self) -> None:
        records = [_make_record() for _ in range(3)]
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = records
        session = MagicMock()
        session.execute = AsyncMock(return_value=list_result)
        service = EventQueryService(session)  # type: ignore[arg-type]
        report = await service.verify_integrity("tenant-acme")
        assert report.total_checked == 3
        assert report.is_clean is True

    async def test_empty_tenant_clean_report(self) -> None:
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []
        session = MagicMock()
        session.execute = AsyncMock(return_value=list_result)
        service = EventQueryService(session)  # type: ignore[arg-type]
        report = await service.verify_integrity("empty-tenant")
        assert report.is_clean is True
        assert report.total_checked == 0

    async def test_tampered_record_detected(self) -> None:
        records = [_make_record() for _ in range(2)]
        records[0].payload_hash = "bad" + "0" * 61
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = records
        session = MagicMock()
        session.execute = AsyncMock(return_value=list_result)
        service = EventQueryService(session)  # type: ignore[arg-type]
        report = await service.verify_integrity("tenant-acme")
        assert report.failed == 1
        assert report.is_clean is False
