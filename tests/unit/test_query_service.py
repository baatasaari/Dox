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


class TestListEventsOptionalFilters:
    async def test_session_id_filter_applied(self) -> None:
        session = _make_session_scalars([])
        service = EventQueryService(session)  # type: ignore[arg-type]
        filters = EventFilter(tenant_id="t", session_id="sess-abc")
        await service.list_events(filters)
        session.execute.assert_awaited_once()

    async def test_from_ts_filter_applied(self) -> None:
        session = _make_session_scalars([])
        service = EventQueryService(session)  # type: ignore[arg-type]
        filters = EventFilter(tenant_id="t", from_ts=datetime.now(UTC))
        await service.list_events(filters)
        session.execute.assert_awaited_once()

    async def test_to_ts_filter_applied(self) -> None:
        session = _make_session_scalars([])
        service = EventQueryService(session)  # type: ignore[arg-type]
        filters = EventFilter(tenant_id="t", to_ts=datetime.now(UTC))
        await service.list_events(filters)
        session.execute.assert_awaited_once()

    async def test_all_optional_filters_at_once(self) -> None:
        records = [_make_record()]
        session = _make_session_scalars(records)
        service = EventQueryService(session)  # type: ignore[arg-type]
        now = datetime.now(UTC)
        filters = EventFilter(
            tenant_id="tenant-acme",
            agent_id="agent-1",
            event_type=EventType.agent_started,
            environment=Environment.dev,
            session_id="sess-1",
            from_ts=now,
            to_ts=now,
        )
        result = await service.list_events(filters)
        assert result == records


class TestCountEventsFilters:
    async def test_count_with_no_filters(self) -> None:
        result = MagicMock()
        result.scalar_one.return_value = 5
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        service = EventQueryService(session)  # type: ignore[arg-type]
        count = await service.count_events(EventFilter(tenant_id="t"))
        assert count == 5

    async def test_count_with_agent_id_filter(self) -> None:
        result = MagicMock()
        result.scalar_one.return_value = 3
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        service = EventQueryService(session)  # type: ignore[arg-type]
        count = await service.count_events(EventFilter(tenant_id="t", agent_id="agent-1"))
        assert count == 3

    async def test_count_with_event_type_filter(self) -> None:
        result = MagicMock()
        result.scalar_one.return_value = 2
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        service = EventQueryService(session)  # type: ignore[arg-type]
        count = await service.count_events(
            EventFilter(tenant_id="t", event_type=EventType.agent_started)
        )
        assert count == 2

    async def test_count_with_environment_filter(self) -> None:
        result = MagicMock()
        result.scalar_one.return_value = 1
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        service = EventQueryService(session)  # type: ignore[arg-type]
        count = await service.count_events(
            EventFilter(tenant_id="t", environment=Environment.prod)
        )
        assert count == 1

    async def test_count_with_session_id_filter(self) -> None:
        result = MagicMock()
        result.scalar_one.return_value = 7
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        service = EventQueryService(session)  # type: ignore[arg-type]
        count = await service.count_events(EventFilter(tenant_id="t", session_id="sess-x"))
        assert count == 7

    async def test_count_with_from_ts_filter(self) -> None:
        result = MagicMock()
        result.scalar_one.return_value = 4
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        service = EventQueryService(session)  # type: ignore[arg-type]
        count = await service.count_events(EventFilter(tenant_id="t", from_ts=datetime.now(UTC)))
        assert count == 4

    async def test_count_with_to_ts_filter(self) -> None:
        result = MagicMock()
        result.scalar_one.return_value = 6
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        service = EventQueryService(session)  # type: ignore[arg-type]
        count = await service.count_events(EventFilter(tenant_id="t", to_ts=datetime.now(UTC)))
        assert count == 6

    async def test_count_with_all_filters(self) -> None:
        result = MagicMock()
        result.scalar_one.return_value = 0
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        service = EventQueryService(session)  # type: ignore[arg-type]
        now = datetime.now(UTC)
        count = await service.count_events(
            EventFilter(
                tenant_id="t",
                agent_id="a",
                event_type=EventType.tool_call_blocked,
                environment=Environment.dev,
                session_id="s",
                from_ts=now,
                to_ts=now,
            )
        )
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
