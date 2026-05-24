"""Module 5 — Sentinel: service layer tests."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common.exceptions import NotFoundError
from common.models.policy import Policy
from common.models.sentinel import SentinelAlert
from common.schemas.enums import EventType, InterventionAction, SentinelType, Severity
from common.schemas.sentinel import PolicyCreate, SentinelAlertCreate
from services.sentinel.service import SentinelService


def _make_session_with_scalar(obj: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock(return_value=None)
    return session


def _make_session_with_scalars(items: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock(return_value=None)
    return session


def _make_alert() -> SentinelAlert:
    return SentinelAlert(
        id=uuid4(),
        tenant_id="tenant-acme",
        agent_id="agent-1",
        sentinel_type="tool_misuse",
        severity="high",
        message="Tool blocked",
    )


def _make_policy() -> Policy:
    return Policy(
        id=uuid4(),
        tenant_id="tenant-acme",
        name="Block misuse",
        sentinel_type="tool_misuse",
        severity="high",
        action="block_tool_call",
    )


def _make_alert_create() -> SentinelAlertCreate:
    return SentinelAlertCreate(
        tenant_id="tenant-acme",
        agent_id="agent-1",
        sentinel_type=SentinelType.tool_misuse,
        severity=Severity.high,
        message="Tool blocked",
    )


class TestCreateAlert:
    async def test_adds_to_session_and_commits(self) -> None:
        session = MagicMock()
        session.commit = AsyncMock()
        service = SentinelService(session)  # type: ignore[arg-type]
        await service.create_alert(_make_alert_create())
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    async def test_returns_sentinel_alert(self) -> None:
        session = MagicMock()
        session.commit = AsyncMock()
        service = SentinelService(session)  # type: ignore[arg-type]
        result = await service.create_alert(_make_alert_create())
        assert isinstance(result, SentinelAlert)

    async def test_alert_fields_match_create(self) -> None:
        session = MagicMock()
        session.commit = AsyncMock()
        service = SentinelService(session)  # type: ignore[arg-type]
        create = _make_alert_create()
        alert = await service.create_alert(create)
        assert alert.tenant_id == create.tenant_id
        assert alert.agent_id == create.agent_id
        assert alert.sentinel_type == create.sentinel_type
        assert alert.severity == create.severity
        assert alert.message == create.message


class TestGetAlert:
    async def test_returns_alert_when_found(self) -> None:
        alert = _make_alert()
        session = _make_session_with_scalar(alert)
        service = SentinelService(session)  # type: ignore[arg-type]
        result = await service.get_alert(alert.id)
        assert result is alert

    async def test_raises_not_found_when_missing(self) -> None:
        session = _make_session_with_scalar(None)
        service = SentinelService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await service.get_alert(uuid4())

    async def test_queries_session(self) -> None:
        alert = _make_alert()
        session = _make_session_with_scalar(alert)
        service = SentinelService(session)  # type: ignore[arg-type]
        await service.get_alert(alert.id)
        session.execute.assert_awaited_once()


class TestListAlerts:
    async def test_returns_list(self) -> None:
        alerts = [_make_alert(), _make_alert()]
        session = _make_session_with_scalars(alerts)
        service = SentinelService(session)  # type: ignore[arg-type]
        result = await service.list_alerts("tenant-acme")
        assert len(result) == 2

    async def test_empty_tenant_returns_empty_list(self) -> None:
        session = _make_session_with_scalars([])
        service = SentinelService(session)  # type: ignore[arg-type]
        result = await service.list_alerts("no-such-tenant")
        assert result == []

    async def test_queries_session_with_filters(self) -> None:
        session = _make_session_with_scalars([])
        service = SentinelService(session)  # type: ignore[arg-type]
        await service.list_alerts(
            "t", severity=Severity.high, is_resolved=False
        )
        session.execute.assert_awaited_once()


class TestResolveAlert:
    async def test_sets_resolved_fields(self) -> None:
        alert = _make_alert()
        session = _make_session_with_scalar(alert)
        service = SentinelService(session)  # type: ignore[arg-type]
        result = await service.resolve_alert(alert.id, InterventionAction.warn)
        assert result.is_resolved is True
        assert result.action_taken == InterventionAction.warn
        assert result.resolved_at is not None

    async def test_resolved_at_is_timezone_aware(self) -> None:
        alert = _make_alert()
        session = _make_session_with_scalar(alert)
        service = SentinelService(session)  # type: ignore[arg-type]
        result = await service.resolve_alert(alert.id, InterventionAction.allow)
        assert result.resolved_at is not None
        assert result.resolved_at.tzinfo is not None

    async def test_raises_not_found_when_missing(self) -> None:
        session = _make_session_with_scalar(None)
        service = SentinelService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await service.resolve_alert(uuid4(), InterventionAction.warn)


class TestCreatePolicy:
    async def test_returns_policy(self) -> None:
        session = MagicMock()
        session.commit = AsyncMock()
        service = SentinelService(session)  # type: ignore[arg-type]
        create = PolicyCreate(
            tenant_id="t",
            name="block",
            sentinel_type=SentinelType.tool_misuse,
            severity=Severity.high,
            action=InterventionAction.block_tool_call,
        )
        result = await service.create_policy(create)
        assert isinstance(result, Policy)
        assert result.name == "block"

    async def test_adds_to_session_and_commits(self) -> None:
        session = MagicMock()
        session.commit = AsyncMock()
        service = SentinelService(session)  # type: ignore[arg-type]
        create = PolicyCreate(
            tenant_id="t",
            name="p",
            sentinel_type=SentinelType.drift,
            severity=Severity.low,
            action=InterventionAction.warn,
        )
        await service.create_policy(create)
        session.add.assert_called_once()
        session.commit.assert_awaited_once()


class TestListPolicies:
    async def test_returns_list(self) -> None:
        policies = [_make_policy()]
        session = _make_session_with_scalars(policies)
        service = SentinelService(session)  # type: ignore[arg-type]
        result = await service.list_policies("tenant-acme")
        assert len(result) == 1

    async def test_empty_returns_empty_list(self) -> None:
        session = _make_session_with_scalars([])
        service = SentinelService(session)  # type: ignore[arg-type]
        result = await service.list_policies("t")
        assert result == []


class TestDeactivatePolicy:
    async def test_sets_is_active_false(self) -> None:
        policy = _make_policy()
        session = _make_session_with_scalar(policy)
        service = SentinelService(session)  # type: ignore[arg-type]
        result = await service.deactivate_policy(policy.id)
        assert result.is_active is False

    async def test_raises_not_found_when_missing(self) -> None:
        session = _make_session_with_scalar(None)
        service = SentinelService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await service.deactivate_policy(uuid4())


class TestEvaluateEvent:
    def _make_event(self, event_type: str) -> object:

        from common.schemas.events import CanonicalEvent

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

    def test_tool_call_blocked_triggers_tool_misuse(self) -> None:
        event = self._make_event(EventType.tool_call_blocked)
        alerts = SentinelService.evaluate_event(event)  # type: ignore[arg-type]
        assert len(alerts) == 1
        assert alerts[0].sentinel_type == SentinelType.tool_misuse
        assert alerts[0].severity == Severity.high

    def test_policy_failed_triggers_policy_breach(self) -> None:
        event = self._make_event(EventType.policy_failed)
        alerts = SentinelService.evaluate_event(event)  # type: ignore[arg-type]
        assert len(alerts) == 1
        assert alerts[0].sentinel_type == SentinelType.policy_breach

    def test_agent_terminated_triggers_critical(self) -> None:
        event = self._make_event(EventType.agent_terminated)
        alerts = SentinelService.evaluate_event(event)  # type: ignore[arg-type]
        assert len(alerts) == 1
        assert alerts[0].severity == Severity.critical

    def test_unknown_event_type_returns_empty(self) -> None:
        event = self._make_event(EventType.agent_started)
        alerts = SentinelService.evaluate_event(event)  # type: ignore[arg-type]
        assert alerts == []

    def test_alert_contains_event_id_and_tenant(self) -> None:
        event = self._make_event(EventType.tool_call_blocked)
        alerts = SentinelService.evaluate_event(event)  # type: ignore[arg-type]
        assert alerts[0].event_id == event.event_id  # type: ignore[union-attr]
        assert alerts[0].tenant_id == event.tenant_id  # type: ignore[union-attr]

    def test_memory_write_blocked_triggers_memory_sentinel(self) -> None:
        event = self._make_event(EventType.memory_write_blocked)
        alerts = SentinelService.evaluate_event(event)  # type: ignore[arg-type]
        assert alerts[0].sentinel_type == SentinelType.memory
