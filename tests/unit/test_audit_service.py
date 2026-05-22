"""Module 16 — Audit Trail: service layer tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common.exceptions import NotFoundError
from common.models.audit_log import AuditEntry
from common.schemas.audit_log import AuditEntryCreate
from services.audit.service import AuditService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    *,
    tenant_id: str = "acme",
    actor_email: str = "alice@example.com",
    action: str = "user.create",
    resource_type: str = "user",
    resource_id: str = "abc123",
    summary: str = "Created user alice@example.com",
) -> AuditEntry:
    return AuditEntry(
        id=uuid4(),
        tenant_id=tenant_id,
        actor_id=uuid4(),
        actor_email=actor_email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        summary=summary,
        extra={"role": "viewer"},
    )


def _scalar_result(obj: object) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    r.scalar_one.return_value = obj
    return r


def _scalars_result(items: list[object]) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _count_result(n: int) -> MagicMock:
    r = MagicMock()
    r.scalar_one.return_value = n
    return r


def _make_session(*results: MagicMock) -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=list(results))
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------


class TestRecord:
    async def test_creates_entry(self) -> None:
        session = _make_session()
        svc = AuditService(session)  # type: ignore[arg-type]
        create = AuditEntryCreate(
            tenant_id="acme",
            actor_email="alice@example.com",
            action="user.create",
            resource_type="user",
            resource_id="u-001",
            summary="Created user alice@example.com",
        )
        entry = await svc.record(create)
        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        assert entry.tenant_id == "acme"
        assert entry.action == "user.create"

    async def test_sets_extra_fields(self) -> None:
        session = _make_session()
        svc = AuditService(session)  # type: ignore[arg-type]
        create = AuditEntryCreate(
            tenant_id="t",
            action="policy.update",
            resource_type="policy",
            resource_id="p-1",
            summary="Updated policy",
            extra={"old_action": "allow", "new_action": "block"},
        )
        entry = await svc.record(create)
        assert entry.extra == {"old_action": "allow", "new_action": "block"}

    async def test_system_actor_when_no_actor_id(self) -> None:
        session = _make_session()
        svc = AuditService(session)  # type: ignore[arg-type]
        create = AuditEntryCreate(
            tenant_id="t",
            action="agent.heartbeat",
            resource_type="agent",
            resource_id="ag-1",
            summary="Agent heartbeat received",
        )
        entry = await svc.record(create)
        assert entry.actor_id is None
        assert entry.actor_email == "system"

    async def test_records_actor_id_when_provided(self) -> None:
        session = _make_session()
        svc = AuditService(session)  # type: ignore[arg-type]
        actor_id = uuid4()
        create = AuditEntryCreate(
            tenant_id="t",
            actor_id=actor_id,
            actor_email="admin@t.com",
            action="tenant.deactivate",
            resource_type="tenant",
            resource_id="t-1",
            summary="Tenant deactivated",
        )
        entry = await svc.record(create)
        assert entry.actor_id == actor_id
        assert entry.actor_email == "admin@t.com"

    async def test_entry_id_is_assigned(self) -> None:
        session = _make_session()
        svc = AuditService(session)  # type: ignore[arg-type]
        create = AuditEntryCreate(
            tenant_id="t",
            action="user.create",
            resource_type="user",
            resource_id="u-1",
            summary="s",
        )
        entry = await svc.record(create)
        assert entry.id is not None


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


class TestGet:
    async def test_returns_entry_when_found(self) -> None:
        e = _make_entry()
        session = _make_session(_scalar_result(e))
        svc = AuditService(session)  # type: ignore[arg-type]
        result = await svc.get(e.id)
        assert result is e

    async def test_raises_not_found_when_missing(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = AuditService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.get(uuid4())


# ---------------------------------------------------------------------------
# list_for_tenant
# ---------------------------------------------------------------------------


class TestListForTenant:
    async def test_returns_all_entries(self) -> None:
        entries = [_make_entry() for _ in range(5)]
        session = _make_session(_scalars_result(entries))
        svc = AuditService(session)  # type: ignore[arg-type]
        result = await svc.list_for_tenant("acme")
        assert len(result) == 5

    async def test_returns_empty_list(self) -> None:
        session = _make_session(_scalars_result([]))
        svc = AuditService(session)  # type: ignore[arg-type]
        result = await svc.list_for_tenant("ghost")
        assert result == []

    async def test_filters_by_action(self) -> None:
        entries = [_make_entry(action="user.create") for _ in range(3)]
        session = _make_session(_scalars_result(entries))
        svc = AuditService(session)  # type: ignore[arg-type]
        result = await svc.list_for_tenant("acme", action="user.create")
        assert all(e.action == "user.create" for e in result)

    async def test_filters_by_resource_type(self) -> None:
        entries = [_make_entry(resource_type="policy") for _ in range(2)]
        session = _make_session(_scalars_result(entries))
        svc = AuditService(session)  # type: ignore[arg-type]
        result = await svc.list_for_tenant("acme", resource_type="policy")
        assert all(e.resource_type == "policy" for e in result)

    async def test_filters_by_actor_id(self) -> None:
        actor_id = uuid4()
        entry = _make_entry()
        entry.actor_id = actor_id  # type: ignore[assignment]
        session = _make_session(_scalars_result([entry]))
        svc = AuditService(session)  # type: ignore[arg-type]
        result = await svc.list_for_tenant("acme", actor_id=actor_id)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# count_for_tenant
# ---------------------------------------------------------------------------


class TestCountForTenant:
    async def test_returns_count(self) -> None:
        session = _make_session(_count_result(7))
        svc = AuditService(session)  # type: ignore[arg-type]
        count = await svc.count_for_tenant("acme")
        assert count == 7

    async def test_returns_zero_for_empty_tenant(self) -> None:
        session = _make_session(_count_result(0))
        svc = AuditService(session)  # type: ignore[arg-type]
        count = await svc.count_for_tenant("ghost")
        assert count == 0

    async def test_filters_propagated_to_count(self) -> None:
        session = _make_session(_count_result(3))
        svc = AuditService(session)  # type: ignore[arg-type]
        count = await svc.count_for_tenant("acme", action="user.create")
        assert count == 3
