"""EventBuilder — fluent factory for CanonicalEvent objects."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from common.schemas.events import CanonicalEvent


class EventBuilder:
    """Stateful builder that constructs CanonicalEvents for a single agent session.

    All events emitted from the same builder share ``trace_id`` and ``session_id``,
    so they can be grouped and replayed as a coherent execution trace.

    Sequence numbers are auto-incremented starting from 1.

    Usage::

        builder = EventBuilder(
            tenant_id="acme",
            agent_id="research-agent",
            agent_version="1.2.0",
        )
        event = builder.tool_call_started("web_search", {"query": "AI news"})
    """

    _SDK_VERSION = "0.1.0"

    def __init__(
        self,
        tenant_id: str,
        agent_id: str,
        agent_version: str,
        *,
        environment: str = "prod",
        session_id: str | None = None,
    ) -> None:
        self._tenant_id = tenant_id
        self._agent_id = agent_id
        self._agent_version = agent_version
        self._environment = environment
        self._session_id: str = session_id or str(uuid4())
        self._trace_id: UUID = uuid4()
        self._sequence: int = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def trace_id(self) -> UUID:
        return self._trace_id

    @property
    def session_id(self) -> str:
        return self._session_id

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def _build(self, event_type: str, payload: dict[str, Any]) -> CanonicalEvent:
        now = datetime.now(UTC)
        return CanonicalEvent(
            event_id=uuid4(),
            trace_id=self._trace_id,
            session_id=self._session_id,
            tenant_id=self._tenant_id,
            agent_id=self._agent_id,
            agent_version=self._agent_version,
            event_type=event_type,
            environment=self._environment,
            timestamp=now,
            client_timestamp=now,
            correlation_id=str(uuid4()),
            sequence_number=self._next_sequence(),
            payload=payload,
            sdk_version=self._SDK_VERSION,
        )

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    def agent_started(self, **payload: Any) -> CanonicalEvent:
        return self._build("agent_started", dict(payload))

    def agent_completed(self, **payload: Any) -> CanonicalEvent:
        return self._build("agent_completed", dict(payload))

    def agent_failed(self, error: str, **payload: Any) -> CanonicalEvent:
        return self._build("agent_failed", {"error": error, **payload})

    def agent_paused(self, reason: str = "", **payload: Any) -> CanonicalEvent:
        return self._build("agent_paused", {"reason": reason, **payload})

    # ------------------------------------------------------------------
    # Tool calls
    # ------------------------------------------------------------------

    def tool_call_started(
        self, tool_name: str, inputs: dict[str, Any], **payload: Any
    ) -> CanonicalEvent:
        return self._build(
            "tool_call_started", {"tool_name": tool_name, "inputs": inputs, **payload}
        )

    def tool_call_completed(
        self, tool_name: str, output: Any, **payload: Any
    ) -> CanonicalEvent:
        return self._build(
            "tool_call_completed", {"tool_name": tool_name, "output": output, **payload}
        )

    def tool_call_failed(self, tool_name: str, error: str, **payload: Any) -> CanonicalEvent:
        return self._build(
            "tool_call_failed", {"tool_name": tool_name, "error": error, **payload}
        )

    def tool_call_blocked(self, tool_name: str, reason: str, **payload: Any) -> CanonicalEvent:
        return self._build(
            "tool_call_blocked", {"tool_name": tool_name, "reason": reason, **payload}
        )

    # ------------------------------------------------------------------
    # Model calls
    # ------------------------------------------------------------------

    def model_called(self, model: str, prompt_tokens: int, **payload: Any) -> CanonicalEvent:
        return self._build(
            "model_called", {"model": model, "prompt_tokens": prompt_tokens, **payload}
        )

    def model_response_received(
        self, model: str, completion_tokens: int, **payload: Any
    ) -> CanonicalEvent:
        return self._build(
            "model_response_received",
            {"model": model, "completion_tokens": completion_tokens, **payload},
        )

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    def memory_read(self, key: str, **payload: Any) -> CanonicalEvent:
        return self._build("memory_read", {"key": key, **payload})

    def memory_write_requested(self, key: str, **payload: Any) -> CanonicalEvent:
        return self._build("memory_write_requested", {"key": key, **payload})

    def memory_write_approved(self, key: str, **payload: Any) -> CanonicalEvent:
        return self._build("memory_write_approved", {"key": key, **payload})

    def memory_write_blocked(self, key: str, reason: str, **payload: Any) -> CanonicalEvent:
        return self._build(
            "memory_write_blocked", {"key": key, "reason": reason, **payload}
        )

    # ------------------------------------------------------------------
    # Custom
    # ------------------------------------------------------------------

    def custom(self, event_type: str, payload: dict[str, Any]) -> CanonicalEvent:
        """Emit any valid EventType not covered by the named helpers."""
        return self._build(event_type, payload)
