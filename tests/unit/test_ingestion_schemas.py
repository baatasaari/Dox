"""Module 3 — Ingestion: request/response schema tests."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from common.schemas.events import CanonicalEvent
from services.ingestion.schemas import (
    BatchIngestRequest,
    BatchIngestResponse,
    IngestResponse,
)


def _make_event() -> CanonicalEvent:
    now = datetime.now(UTC)
    return CanonicalEvent(
        event_id=uuid4(),
        trace_id=uuid4(),
        session_id="s1",
        tenant_id="t1",
        agent_id="a1",
        agent_version="1.0",
        event_type="agent_started",
        environment="dev",
        timestamp=now,
        client_timestamp=now,
        correlation_id="c1",
        payload={},
    )


class TestIngestResponse:
    def test_requires_event_id(self) -> None:
        eid = uuid4()
        r = IngestResponse(event_id=eid)
        assert r.event_id == eid

    def test_status_defaults_to_accepted(self) -> None:
        r = IngestResponse(event_id=uuid4())
        assert r.status == "accepted"

    def test_received_at_defaults_to_utc_now(self) -> None:
        before = datetime.now(UTC)
        r = IngestResponse(event_id=uuid4())
        assert r.received_at >= before
        assert r.received_at.tzinfo is not None

    def test_serialises_to_valid_json(self) -> None:
        r = IngestResponse(event_id=uuid4())
        parsed = json.loads(r.model_dump_json())
        assert parsed["status"] == "accepted"
        assert "event_id" in parsed


class TestBatchIngestRequest:
    def test_valid_single_event(self) -> None:
        req = BatchIngestRequest(events=[_make_event()])
        assert len(req.events) == 1

    def test_valid_multiple_events(self) -> None:
        req = BatchIngestRequest(events=[_make_event() for _ in range(5)])
        assert len(req.events) == 5

    def test_empty_list_raises(self) -> None:
        with pytest.raises(ValidationError):
            BatchIngestRequest(events=[])

    def test_exceeds_100_raises(self) -> None:
        with pytest.raises(ValidationError):
            BatchIngestRequest(events=[_make_event() for _ in range(101)])

    def test_exactly_100_accepted(self) -> None:
        req = BatchIngestRequest(events=[_make_event() for _ in range(100)])
        assert len(req.events) == 100


class TestBatchIngestResponse:
    def test_accepted_count_and_event_ids(self) -> None:
        ids = [uuid4(), uuid4()]
        r = BatchIngestResponse(accepted=2, event_ids=ids)
        assert r.accepted == 2
        assert r.event_ids == ids

    def test_rejected_defaults_to_zero(self) -> None:
        r = BatchIngestResponse(accepted=1, event_ids=[uuid4()])
        assert r.rejected == 0
