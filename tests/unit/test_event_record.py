"""Module 3 — EventRecord model: from_canonical tests."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from common.models.event import EventRecord
from common.schemas.events import CanonicalEvent


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


class TestEventRecordFromCanonical:
    def test_event_id_mapped(self, canonical: CanonicalEvent) -> None:
        record = EventRecord.from_canonical(canonical)
        assert record.event_id == canonical.event_id

    def test_trace_id_mapped(self, canonical: CanonicalEvent) -> None:
        record = EventRecord.from_canonical(canonical)
        assert record.trace_id == canonical.trace_id

    def test_all_identity_fields_mapped(self, canonical: CanonicalEvent) -> None:
        record = EventRecord.from_canonical(canonical)
        assert record.session_id == canonical.session_id
        assert record.tenant_id == canonical.tenant_id
        assert record.agent_id == canonical.agent_id
        assert record.agent_version == canonical.agent_version

    def test_event_type_is_string(self, canonical: CanonicalEvent) -> None:
        record = EventRecord.from_canonical(canonical)
        assert record.event_type == "agent_started"
        assert isinstance(record.event_type, str)

    def test_timestamps_preserved(self, canonical: CanonicalEvent) -> None:
        record = EventRecord.from_canonical(canonical)
        assert record.timestamp == canonical.timestamp
        assert record.client_timestamp == canonical.client_timestamp

    def test_payload_preserved(self, canonical: CanonicalEvent) -> None:
        record = EventRecord.from_canonical(canonical)
        assert record.payload == canonical.payload

    def test_payload_hash_computed_when_not_provided(self, canonical: CanonicalEvent) -> None:
        assert canonical.payload_hash is None
        record = EventRecord.from_canonical(canonical)
        assert record.payload_hash is not None
        assert len(record.payload_hash) == 64

    def test_existing_payload_hash_preserved(self, canonical: CanonicalEvent) -> None:
        hash_val = "a" * 64
        event_with_hash = canonical.model_copy(update={"payload_hash": hash_val})
        record = EventRecord.from_canonical(event_with_hash)
        assert record.payload_hash == hash_val

    def test_raw_event_is_json_dict(self, canonical: CanonicalEvent) -> None:
        record = EventRecord.from_canonical(canonical)
        assert isinstance(record.raw_event, dict)

    def test_raw_event_contains_event_id_as_string(self, canonical: CanonicalEvent) -> None:
        record = EventRecord.from_canonical(canonical)
        assert record.raw_event["event_id"] == str(canonical.event_id)

    def test_id_is_uuid_and_auto_generated(self, canonical: CanonicalEvent) -> None:
        r1 = EventRecord.from_canonical(canonical)
        r2 = EventRecord.from_canonical(
            canonical.model_copy(update={"event_id": uuid4()})
        )
        assert isinstance(r1.id, UUID)
        assert r1.id != r2.id

    def test_schema_version_mapped(self, canonical: CanonicalEvent) -> None:
        record = EventRecord.from_canonical(canonical)
        assert record.schema_version == "1.0"
