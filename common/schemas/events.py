from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from common.schemas.enums import Environment, EventType
from common.schemas.validators import (
    validate_payload_hash as _validate_hash,
)
from common.schemas.validators import (
    validate_schema_version as _validate_schema_version,
)
from common.schemas.validators import (
    validate_traceparent as _validate_traceparent,
)

# ---------------------------------------------------------------------------
# Re-export validators under simpler names used in field_validators below
# ---------------------------------------------------------------------------
_FIVE_MINUTES = timedelta(minutes=5)


class CanonicalEvent(BaseModel):
    """Canonical event schema — the contract shared by every Dox service.

    All services read and write this model. The schema version field allows
    the normalisation layer to handle multiple schema generations simultaneously.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_default=True,
        use_enum_values=True,
    )

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    event_id: UUID
    schema_version: str = "1.0"
    trace_id: UUID
    parent_trace_id: UUID | None = None
    session_id: str = Field(min_length=1, max_length=255)
    tenant_id: str = Field(min_length=1, max_length=255)
    agent_id: str = Field(min_length=1, max_length=255)
    agent_version: str = Field(min_length=1, max_length=100)
    agent_fingerprint: str | None = Field(default=None, min_length=32, max_length=255)

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------
    event_type: EventType
    environment: Environment
    timestamp: AwareDatetime          # server receipt time — always timezone-aware
    client_timestamp: AwareDatetime   # SDK emission time — always timezone-aware
    sequence_number: int | None = Field(default=None, ge=0)

    # ------------------------------------------------------------------
    # Linking
    # ------------------------------------------------------------------
    parent_event_id: UUID | None = None
    correlation_id: str = Field(min_length=1, max_length=255)
    replay_session_id: UUID | None = None

    # ------------------------------------------------------------------
    # Distributed tracing (W3C TraceContext)
    # ------------------------------------------------------------------
    traceparent: str | None = None
    tracestate: str | None = Field(default=None, max_length=1024)

    # ------------------------------------------------------------------
    # Payload
    # ------------------------------------------------------------------
    payload: dict[str, Any]
    raw_payload: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Integrity — hash chain
    # ------------------------------------------------------------------
    payload_hash: str | None = None
    previous_event_hash: str | None = None

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------
    user_id: str | None = Field(default=None, max_length=255)
    consent_id: str | None = Field(default=None, max_length=255)
    purpose_id: str | None = Field(default=None, max_length=255)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    sdk_version: str | None = Field(default=None, max_length=50)
    adapter_id: str | None = Field(default=None, max_length=100)
    tags: dict[str, str] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # Field validators
    # ------------------------------------------------------------------

    @field_validator("schema_version")
    @classmethod
    def check_schema_version(cls, v: str) -> str:
        return _validate_schema_version(v)

    @field_validator("traceparent")
    @classmethod
    def check_traceparent(cls, v: str | None) -> str | None:
        return _validate_traceparent(v)

    @field_validator("payload_hash", "previous_event_hash")
    @classmethod
    def check_hash(cls, v: str | None) -> str | None:
        return _validate_hash(v)

    @field_validator("tags")
    @classmethod
    def check_tags(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 50:
            raise ValueError("tags cannot have more than 50 entries")
        for key, value in v.items():
            if len(key) > 100:
                raise ValueError(
                    f"tag key '{key[:20]}...' exceeds maximum length of 100 characters"
                )
            if len(value) > 500:
                raise ValueError(
                    f"tag value for key '{key}' exceeds maximum length of 500 characters"
                )
        return v

    # ------------------------------------------------------------------
    # Model-level validator
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def check_timestamp_ordering(self) -> CanonicalEvent:
        """client_timestamp must not be more than 5 minutes ahead of server timestamp.

        A larger gap indicates a severely wrong client clock or a replayed event.
        """
        delta = self.client_timestamp - self.timestamp
        if delta > _FIVE_MINUTES:
            raise ValueError(
                "client_timestamp cannot be more than 5 minutes in the future "
                f"relative to server timestamp (delta: {delta})"
            )
        return self
