"""Integration: Ingestion → Sentinel → Policy evaluation loop."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from common.adapters.event_bus import InMemoryEventBusAdapter
from common.adapters.metrics import InMemoryMetricsAdapter
from common.models.policy import Policy
from common.models.sentinel import SentinelAlert
from common.schemas.enums import (
    EventType,
    InterventionAction,
    SentinelType,
    Severity,
)
from common.schemas.events import CanonicalEvent
from common.schemas.policy import PolicyEvaluateRequest
from services.ingestion.service import IngestionService
from services.policy.service import PolicyEvaluatorService
from services.sentinel.service import SentinelService


def _make_event(event_type: str = EventType.tool_call_blocked) -> CanonicalEvent:
    now = datetime.now(UTC)
    return CanonicalEvent(
        event_id=uuid4(),
        trace_id=uuid4(),
        session_id="sess-1",
        tenant_id="tenant-acme",
        agent_id="agent-1",
        agent_version="1.0.0",
        event_type=event_type,
        environment="dev",
        timestamp=now,
        client_timestamp=now,
        correlation_id="corr-1",
        payload={"step": "test"},
    )


def _make_sentinel_session() -> MagicMock:
    """Mock session for SentinelService — supports add + commit."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _make_ingestion_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


class TestIngestionSentinelLoop:
    async def test_trigger_event_reaches_sentinel(self) -> None:
        # Real SentinelService instance with mock session
        sentinel_session = _make_sentinel_session()
        sentinel_svc = SentinelService(session=sentinel_session)  # type: ignore[arg-type]

        ingestion_svc = IngestionService(
            session=_make_ingestion_session(),  # type: ignore[arg-type]
            event_bus=InMemoryEventBusAdapter(),
            metrics=InMemoryMetricsAdapter(),
            sentinel_service=sentinel_svc,
        )

        event = _make_event(EventType.tool_call_blocked)
        await ingestion_svc.ingest(event)

        # SentinelService.create_alert calls session.add then session.commit
        sentinel_session.add.assert_called_once()
        sentinel_session.commit.assert_awaited_once()

        # The object added is a SentinelAlert
        added = sentinel_session.add.call_args[0][0]
        assert isinstance(added, SentinelAlert)
        assert added.tenant_id == event.tenant_id
        assert added.sentinel_type == SentinelType.tool_misuse

    async def test_alert_severity_matches_trigger_map(self) -> None:
        sentinel_session = _make_sentinel_session()
        sentinel_svc = SentinelService(session=sentinel_session)  # type: ignore[arg-type]

        ingestion_svc = IngestionService(
            session=_make_ingestion_session(),  # type: ignore[arg-type]
            event_bus=InMemoryEventBusAdapter(),
            metrics=InMemoryMetricsAdapter(),
            sentinel_service=sentinel_svc,
        )

        event = _make_event(EventType.agent_terminated)
        await ingestion_svc.ingest(event)

        added = sentinel_session.add.call_args[0][0]
        assert added.severity == Severity.critical

    async def test_non_trigger_event_no_alert(self) -> None:
        sentinel_session = _make_sentinel_session()
        sentinel_svc = SentinelService(session=sentinel_session)  # type: ignore[arg-type]

        ingestion_svc = IngestionService(
            session=_make_ingestion_session(),  # type: ignore[arg-type]
            event_bus=InMemoryEventBusAdapter(),
            metrics=InMemoryMetricsAdapter(),
            sentinel_service=sentinel_svc,
        )

        event = _make_event(EventType.agent_started)
        await ingestion_svc.ingest(event)

        sentinel_session.add.assert_not_called()

    async def test_policy_call_blocked_sentinel_type_is_tool_misuse(self) -> None:
        sentinel_session = _make_sentinel_session()
        sentinel_svc = SentinelService(session=sentinel_session)  # type: ignore[arg-type]

        ingestion_svc = IngestionService(
            session=_make_ingestion_session(),  # type: ignore[arg-type]
            event_bus=InMemoryEventBusAdapter(),
            metrics=InMemoryMetricsAdapter(),
            sentinel_service=sentinel_svc,
        )

        event = _make_event(EventType.tool_call_blocked)
        await ingestion_svc.ingest(event)

        added = sentinel_session.add.call_args[0][0]
        assert added.sentinel_type == SentinelType.tool_misuse
        assert added.severity == Severity.high

    async def test_policy_failed_event_creates_policy_breach_alert(self) -> None:
        sentinel_session = _make_sentinel_session()
        sentinel_svc = SentinelService(session=sentinel_session)  # type: ignore[arg-type]

        ingestion_svc = IngestionService(
            session=_make_ingestion_session(),  # type: ignore[arg-type]
            event_bus=InMemoryEventBusAdapter(),
            metrics=InMemoryMetricsAdapter(),
            sentinel_service=sentinel_svc,
        )

        event = _make_event(EventType.policy_failed)
        await ingestion_svc.ingest(event)

        added = sentinel_session.add.call_args[0][0]
        assert added.sentinel_type == SentinelType.policy_breach
        assert added.severity == Severity.high

    async def test_alert_agent_id_matches_event(self) -> None:
        sentinel_session = _make_sentinel_session()
        sentinel_svc = SentinelService(session=sentinel_session)  # type: ignore[arg-type]

        ingestion_svc = IngestionService(
            session=_make_ingestion_session(),  # type: ignore[arg-type]
            event_bus=InMemoryEventBusAdapter(),
            metrics=InMemoryMetricsAdapter(),
            sentinel_service=sentinel_svc,
        )

        event = _make_event(EventType.tool_call_blocked)
        await ingestion_svc.ingest(event)

        added = sentinel_session.add.call_args[0][0]
        assert added.agent_id == event.agent_id

    async def test_alert_event_id_matches_event(self) -> None:
        sentinel_session = _make_sentinel_session()
        sentinel_svc = SentinelService(session=sentinel_session)  # type: ignore[arg-type]

        ingestion_svc = IngestionService(
            session=_make_ingestion_session(),  # type: ignore[arg-type]
            event_bus=InMemoryEventBusAdapter(),
            metrics=InMemoryMetricsAdapter(),
            sentinel_service=sentinel_svc,
        )

        event = _make_event(EventType.tool_call_blocked)
        await ingestion_svc.ingest(event)

        added = sentinel_session.add.call_args[0][0]
        assert added.event_id == event.event_id

    async def test_no_sentinel_service_skips_alert(self) -> None:
        """IngestionService with no sentinel_service runs without error."""
        ingestion_svc = IngestionService(
            session=_make_ingestion_session(),  # type: ignore[arg-type]
            event_bus=InMemoryEventBusAdapter(),
            metrics=InMemoryMetricsAdapter(),
            sentinel_service=None,
        )

        event = _make_event(EventType.tool_call_blocked)
        record = await ingestion_svc.ingest(event)
        # Returns a valid record even without sentinel
        assert record.event_id == event.event_id

    async def test_policy_evaluation_after_alert(self) -> None:
        # After an alert is created for tool_misuse/high, evaluate policies
        matching_policy = Policy(
            id=uuid4(),
            tenant_id="tenant-acme",
            name="block-tools",
            sentinel_type=SentinelType.tool_misuse,
            severity=Severity.medium,  # threshold: medium → matches high request
            action=InterventionAction.block_tool_call,
            is_active=True,
        )

        scalars_result = MagicMock()
        scalars_result.scalars.return_value.all.return_value = [matching_policy]
        policy_session = MagicMock()
        policy_session.execute = AsyncMock(return_value=scalars_result)

        policy_svc = PolicyEvaluatorService(session=policy_session)  # type: ignore[arg-type]

        # The alert from ingesting tool_call_blocked would be: tool_misuse / high
        result = await policy_svc.evaluate(
            PolicyEvaluateRequest(
                tenant_id="tenant-acme",
                sentinel_type=SentinelType.tool_misuse,
                severity=Severity.high,
            )
        )

        assert result.matched_count == 1
        assert result.action == InterventionAction.block_tool_call
        assert result.is_blocked is True

    async def test_no_matching_policy_defaults_to_allow(self) -> None:
        scalars_result = MagicMock()
        scalars_result.scalars.return_value.all.return_value = []
        policy_session = MagicMock()
        policy_session.execute = AsyncMock(return_value=scalars_result)

        policy_svc = PolicyEvaluatorService(session=policy_session)  # type: ignore[arg-type]

        result = await policy_svc.evaluate(
            PolicyEvaluateRequest(
                tenant_id="tenant-acme",
                sentinel_type=SentinelType.tool_misuse,
                severity=Severity.high,
            )
        )

        assert result.action == InterventionAction.allow
        assert result.is_blocked is False

    async def test_policy_severity_threshold_high_matches_medium_policy(self) -> None:
        """A policy with severity=medium is matched by an alert with severity=high."""
        medium_policy = Policy(
            id=uuid4(),
            tenant_id="tenant-acme",
            name="warn-medium",
            sentinel_type=SentinelType.tool_misuse,
            severity=Severity.medium,
            action=InterventionAction.warn,
            is_active=True,
        )

        scalars_result = MagicMock()
        scalars_result.scalars.return_value.all.return_value = [medium_policy]
        policy_session = MagicMock()
        policy_session.execute = AsyncMock(return_value=scalars_result)

        policy_svc = PolicyEvaluatorService(session=policy_session)  # type: ignore[arg-type]

        result = await policy_svc.evaluate(
            PolicyEvaluateRequest(
                tenant_id="tenant-acme",
                sentinel_type=SentinelType.tool_misuse,
                severity=Severity.high,
            )
        )

        assert result.matched_count == 1
        assert result.action == InterventionAction.warn

    async def test_policy_severity_threshold_low_not_matched_by_medium_policy(self) -> None:
        """A policy with severity=high is NOT matched by an alert with severity=low."""
        high_policy = Policy(
            id=uuid4(),
            tenant_id="tenant-acme",
            name="block-high",
            sentinel_type=SentinelType.tool_misuse,
            severity=Severity.high,
            action=InterventionAction.block_tool_call,
            is_active=True,
        )

        scalars_result = MagicMock()
        scalars_result.scalars.return_value.all.return_value = [high_policy]
        policy_session = MagicMock()
        policy_session.execute = AsyncMock(return_value=scalars_result)

        policy_svc = PolicyEvaluatorService(session=policy_session)  # type: ignore[arg-type]

        result = await policy_svc.evaluate(
            PolicyEvaluateRequest(
                tenant_id="tenant-acme",
                sentinel_type=SentinelType.tool_misuse,
                severity=Severity.low,
            )
        )

        # high policy not matched by low severity alert
        assert result.matched_count == 0
        assert result.action == InterventionAction.allow

    async def test_multiple_trigger_event_types_each_create_one_alert(self) -> None:
        """Each trigger event type maps to exactly one alert via evaluate_event."""
        trigger_events = [
            EventType.tool_call_blocked,
            EventType.tool_call_failed,
            EventType.policy_failed,
            EventType.memory_write_blocked,
            EventType.memory_rollback,
            EventType.agent_failed,
            EventType.agent_terminated,
        ]

        for event_type in trigger_events:
            sentinel_session = _make_sentinel_session()
            sentinel_svc = SentinelService(session=sentinel_session)  # type: ignore[arg-type]

            ingestion_svc = IngestionService(
                session=_make_ingestion_session(),  # type: ignore[arg-type]
                event_bus=InMemoryEventBusAdapter(),
                metrics=InMemoryMetricsAdapter(),
                sentinel_service=sentinel_svc,
            )

            event = _make_event(event_type)
            await ingestion_svc.ingest(event)

            assert sentinel_session.add.call_count == 1, (
                f"Expected 1 alert for {event_type}, got {sentinel_session.add.call_count}"
            )
            assert sentinel_session.commit.await_count == 1
