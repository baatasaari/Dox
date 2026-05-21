"""Module 1 — Event Schema: Serialisation and round-trip tests."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from common.schemas.events import CanonicalEvent


@pytest.fixture()
def event() -> CanonicalEvent:
    now = datetime.now(UTC)
    return CanonicalEvent(
        event_id=uuid4(),
        trace_id=uuid4(),
        session_id="session-001",
        tenant_id="tenant-acme",
        agent_id="financial-agent",
        agent_version="1.0.0",
        event_type="agent_started",
        environment="dev",
        timestamp=now,
        client_timestamp=now,
        correlation_id="corr-001",
        payload={"step": "initialise", "depth": 1},
        tags={"region": "eu-west"},
    )


class TestSerialisation:
    def test_model_dump_returns_dict(self, event: CanonicalEvent) -> None:
        result = event.model_dump()
        assert isinstance(result, dict)

    def test_model_dump_json_returns_valid_json_string(self, event: CanonicalEvent) -> None:
        json_str = event.model_dump_json()
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)

    def test_dict_round_trip_preserves_all_fields(self, event: CanonicalEvent) -> None:
        d = event.model_dump()
        event2 = CanonicalEvent(**d)
        assert event2.event_id == event.event_id
        assert event2.trace_id == event.trace_id
        assert event2.event_type == event.event_type
        assert event2.tags == event.tags
        assert event2.payload == event.payload

    def test_json_round_trip_preserves_all_fields(self, event: CanonicalEvent) -> None:
        json_str = event.model_dump_json()
        event2 = CanonicalEvent.model_validate_json(json_str)
        assert event2.event_id == event.event_id
        assert event2.environment == event.environment
        assert event2.schema_version == event.schema_version

    def test_uuid_fields_serialise_as_strings_in_json(self, event: CanonicalEvent) -> None:
        d = json.loads(event.model_dump_json())
        uuid_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        assert uuid_pattern.match(d["event_id"]), "event_id must serialise as UUID string"
        assert uuid_pattern.match(d["trace_id"]), "trace_id must serialise as UUID string"

    def test_datetime_fields_serialise_as_iso_strings_with_timezone(
        self, event: CanonicalEvent
    ) -> None:
        d = json.loads(event.model_dump_json())
        ts = d["timestamp"]
        assert isinstance(ts, str)
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None, "timestamp must include timezone in JSON"

    def test_event_type_serialises_as_string_not_enum(self, event: CanonicalEvent) -> None:
        d = event.model_dump()
        assert d["event_type"] == "agent_started"
        assert isinstance(d["event_type"], str)

    def test_none_optional_fields_excluded_with_exclude_none(self, event: CanonicalEvent) -> None:
        d = event.model_dump(exclude_none=True)
        assert "parent_event_id" not in d
        assert "parent_trace_id" not in d
        assert "traceparent" not in d
        assert "user_id" not in d

    def test_model_validate_accepts_dict(self, event: CanonicalEvent) -> None:
        d = event.model_dump()
        event2 = CanonicalEvent.model_validate(d)
        assert event2.event_id == event.event_id

    def test_model_validate_json_accepts_json_string(self, event: CanonicalEvent) -> None:
        json_str = event.model_dump_json()
        event2 = CanonicalEvent.model_validate_json(json_str)
        assert event2.tenant_id == event.tenant_id
