"""Module 1 — Event Schema: CanonicalEvent model tests."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from common.schemas.enums import Environment, EventType
from common.schemas.events import CanonicalEvent

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def valid_dict() -> dict:  # type: ignore[type-arg]
    """Minimal valid event dict — all required fields, no optional ones."""
    now = datetime.now(UTC)
    return {
        "event_id": str(uuid4()),
        "trace_id": str(uuid4()),
        "session_id": "session-001",
        "tenant_id": "tenant-acme",
        "agent_id": "financial-agent",
        "agent_version": "1.0.0",
        "event_type": "agent_started",
        "environment": "dev",
        "timestamp": now.isoformat(),
        "client_timestamp": now.isoformat(),
        "correlation_id": "corr-001",
        "payload": {"step": "initialise"},
    }


# ---------------------------------------------------------------------------
# Happy-path construction
# ---------------------------------------------------------------------------

class TestValidEventConstruction:
    def test_minimal_valid_event_passes(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        event = CanonicalEvent(**valid_dict)
        assert event.event_type == "agent_started"
        assert event.environment == "dev"

    def test_schema_version_defaults_to_1_0(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        event = CanonicalEvent(**valid_dict)
        assert event.schema_version == "1.0"

    def test_tags_default_to_empty_dict(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        event = CanonicalEvent(**valid_dict)
        assert event.tags == {}

    def test_optional_fields_default_to_none(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        event = CanonicalEvent(**valid_dict)
        assert event.parent_event_id is None
        assert event.parent_trace_id is None
        assert event.replay_session_id is None
        assert event.traceparent is None
        assert event.tracestate is None
        assert event.user_id is None
        assert event.consent_id is None
        assert event.purpose_id is None
        assert event.sdk_version is None
        assert event.adapter_id is None
        assert event.payload_hash is None
        assert event.previous_event_hash is None
        assert event.sequence_number is None
        assert event.agent_fingerprint is None

    def test_all_34_event_types_are_accepted(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        for event_type in EventType:
            valid_dict["event_id"] = str(uuid4())
            valid_dict["event_type"] = event_type.value
            event = CanonicalEvent(**valid_dict)
            assert event.event_type == event_type.value

    def test_all_four_environments_are_accepted(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        for env in Environment:
            valid_dict["event_id"] = str(uuid4())
            valid_dict["environment"] = env.value
            event = CanonicalEvent(**valid_dict)
            assert event.environment == env.value

    def test_string_uuid_coerced_to_uuid_type(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        event = CanonicalEvent(**valid_dict)
        assert isinstance(event.event_id, UUID)
        assert isinstance(event.trace_id, UUID)

    def test_whitespace_stripped_from_session_id(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["session_id"] = "  session-1  "
        event = CanonicalEvent(**valid_dict)
        assert event.session_id == "session-1"

    def test_event_type_stored_as_string_value(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        """use_enum_values=True means the field holds the string, not the enum."""
        event = CanonicalEvent(**valid_dict)
        assert event.event_type == "agent_started"
        assert not isinstance(event.event_type, EventType)

    def test_payload_can_be_empty_dict(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["payload"] = {}
        event = CanonicalEvent(**valid_dict)
        assert event.payload == {}

    def test_tags_with_valid_entries_accepted(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["tags"] = {"env": "prod", "team": "fintech"}
        event = CanonicalEvent(**valid_dict)
        assert event.tags == {"env": "prod", "team": "fintech"}

    def test_sequence_number_zero_accepted(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["sequence_number"] = 0
        event = CanonicalEvent(**valid_dict)
        assert event.sequence_number == 0

    def test_valid_payload_hash_accepted(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["payload_hash"] = "a" * 64
        event = CanonicalEvent(**valid_dict)
        assert event.payload_hash == "a" * 64

    def test_valid_traceparent_accepted(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["traceparent"] = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        event = CanonicalEvent(**valid_dict)
        assert event.traceparent == "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

    def test_client_timestamp_exactly_5_min_ahead_accepted(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        now = datetime.now(UTC)
        valid_dict["timestamp"] = now.isoformat()
        valid_dict["client_timestamp"] = (now + timedelta(minutes=5)).isoformat()
        event = CanonicalEvent(**valid_dict)
        assert event.client_timestamp > event.timestamp


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------

class TestMissingRequiredFields:
    REQUIRED = [
        "event_id", "trace_id", "session_id", "tenant_id",
        "agent_id", "agent_version", "event_type", "environment",
        "timestamp", "client_timestamp", "correlation_id", "payload",
    ]

    @pytest.mark.parametrize("field", REQUIRED)
    def test_missing_field_raises_validation_error(
        self, valid_dict: dict, field: str  # type: ignore[type-arg]
    ) -> None:
        del valid_dict[field]
        with pytest.raises(ValidationError) as exc_info:
            CanonicalEvent(**valid_dict)
        locations = [e["loc"] for e in exc_info.value.errors()]
        assert any(field in str(loc) for loc in locations), (
            f"Expected error mentioning '{field}', got: {locations}"
        )


# ---------------------------------------------------------------------------
# Invalid field values
# ---------------------------------------------------------------------------

class TestInvalidFieldValues:
    def test_invalid_event_type_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["event_type"] = "made_up_event"
        with pytest.raises(ValidationError) as exc_info:
            CanonicalEvent(**valid_dict)
        assert any("event_type" in str(e["loc"]) for e in exc_info.value.errors())

    def test_invalid_environment_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["environment"] = "production"
        with pytest.raises(ValidationError) as exc_info:
            CanonicalEvent(**valid_dict)
        assert any("environment" in str(e["loc"]) for e in exc_info.value.errors())

    def test_extra_unknown_field_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["unknown_field"] = "surprise"
        with pytest.raises(ValidationError) as exc_info:
            CanonicalEvent(**valid_dict)
        assert any("unknown_field" in str(e["loc"]) for e in exc_info.value.errors())

    def test_invalid_uuid_format_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["event_id"] = "not-a-uuid"
        with pytest.raises(ValidationError) as exc_info:
            CanonicalEvent(**valid_dict)
        assert any("event_id" in str(e["loc"]) for e in exc_info.value.errors())

    def test_empty_session_id_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["session_id"] = ""
        with pytest.raises(ValidationError) as exc_info:
            CanonicalEvent(**valid_dict)
        assert any("session_id" in str(e["loc"]) for e in exc_info.value.errors())

    def test_whitespace_only_session_id_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        # After str_strip_whitespace=True, "   " becomes "" which fails min_length=1
        valid_dict["session_id"] = "   "
        with pytest.raises(ValidationError):
            CanonicalEvent(**valid_dict)

    def test_naive_timestamp_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["timestamp"] = "2024-01-01T12:00:00"  # no tzinfo
        with pytest.raises(ValidationError) as exc_info:
            CanonicalEvent(**valid_dict)
        assert any("timestamp" in str(e["loc"]) for e in exc_info.value.errors())

    def test_naive_client_timestamp_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["client_timestamp"] = "2024-01-01T12:00:00"
        with pytest.raises(ValidationError) as exc_info:
            CanonicalEvent(**valid_dict)
        assert any("client_timestamp" in str(e["loc"]) for e in exc_info.value.errors())

    def test_payload_as_list_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["payload"] = [1, 2, 3]
        with pytest.raises(ValidationError) as exc_info:
            CanonicalEvent(**valid_dict)
        assert any("payload" in str(e["loc"]) for e in exc_info.value.errors())

    def test_payload_as_string_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["payload"] = "just a string"
        with pytest.raises(ValidationError):
            CanonicalEvent(**valid_dict)

    def test_invalid_payload_hash_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["payload_hash"] = "tooshort"
        with pytest.raises(ValidationError) as exc_info:
            CanonicalEvent(**valid_dict)
        assert any("payload_hash" in str(e["loc"]) for e in exc_info.value.errors())

    def test_invalid_traceparent_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["traceparent"] = "invalid-traceparent"
        with pytest.raises(ValidationError) as exc_info:
            CanonicalEvent(**valid_dict)
        assert any("traceparent" in str(e["loc"]) for e in exc_info.value.errors())

    def test_negative_sequence_number_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["sequence_number"] = -1
        with pytest.raises(ValidationError) as exc_info:
            CanonicalEvent(**valid_dict)
        assert any("sequence_number" in str(e["loc"]) for e in exc_info.value.errors())

    def test_tags_exceeding_50_entries_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["tags"] = {str(i): "v" for i in range(51)}
        with pytest.raises(ValidationError) as exc_info:
            CanonicalEvent(**valid_dict)
        assert any("tags" in str(e["loc"]) for e in exc_info.value.errors())

    def test_tag_key_exceeding_100_chars_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["tags"] = {"k" * 101: "value"}
        with pytest.raises(ValidationError):
            CanonicalEvent(**valid_dict)

    def test_tag_value_exceeding_500_chars_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["tags"] = {"key": "v" * 501}
        with pytest.raises(ValidationError):
            CanonicalEvent(**valid_dict)

    def test_client_timestamp_more_than_5_min_ahead_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        now = datetime.now(UTC)
        valid_dict["timestamp"] = now.isoformat()
        valid_dict["client_timestamp"] = (now + timedelta(minutes=5, seconds=1)).isoformat()
        with pytest.raises(ValidationError) as exc_info:
            CanonicalEvent(**valid_dict)
        assert "5 minutes" in str(exc_info.value)

    def test_invalid_schema_version_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["schema_version"] = "1.0.0"
        with pytest.raises(ValidationError) as exc_info:
            CanonicalEvent(**valid_dict)
        assert any("schema_version" in str(e["loc"]) for e in exc_info.value.errors())

    def test_agent_fingerprint_too_short_raises(self, valid_dict: dict) -> None:  # type: ignore[type-arg]
        valid_dict["agent_fingerprint"] = "tooshort"  # < 32 chars
        with pytest.raises(ValidationError):
            CanonicalEvent(**valid_dict)
