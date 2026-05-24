"""Module 16 — Audit Trail: integration tests with real service instances."""
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
    tenant_id: str = "acme",
    action: str = "user.create",
    resource_type: str = "user",
) -> AuditEntry:
    return AuditEntry(
        id=uuid4(),
        tenant_id=tenant_id,
        actor_id=uuid4(),
        actor_email="alice@example.com",
        action=action,
        resource_type=resource_type,
        resource_id=str(uuid4()),
        summary=f"{action} on {resource_type}",
        extra={"env": "test"},
    )


def _scalar_session(obj: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    result.scalar_one.return_value = obj
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _scalars_session(items: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _multi_session(*results: MagicMock) -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=list(results))
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


class TestRecording:
    async def test_record_commits_and_returns_entry(self) -> None:
        session = _scalar_session(None)
        svc = AuditService(session)  # type: ignore[arg-type]
        create = AuditEntryCreate(
            tenant_id="acme",
            actor_email="admin@acme.com",
            action="tenant.create",
            resource_type="tenant",
            resource_id="t-001",
            summary="Created tenant acme",
        )
        entry = await svc.record(create)
        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        assert entry.action == "tenant.create"
        assert entry.resource_type == "tenant"

    async def test_record_preserves_extra_metadata(self) -> None:
        session = _scalar_session(None)
        svc = AuditService(session)  # type: ignore[arg-type]
        create = AuditEntryCreate(
            tenant_id="acme",
            action="policy.update",
            resource_type="policy",
            resource_id="p-1",
            summary="Policy updated",
            extra={"old_tier": "starter", "new_tier": "professional"},
        )
        entry = await svc.record(create)
        assert entry.extra["old_tier"] == "starter"
        assert entry.extra["new_tier"] == "professional"

    async def test_multiple_records_separate_commits(self) -> None:
        session = MagicMock()
        session.execute = AsyncMock(return_value=MagicMock())
        session.add = MagicMock()
        session.commit = AsyncMock()
        svc = AuditService(session)  # type: ignore[arg-type]

        for action in ("user.create", "user.deactivate", "policy.create"):
            await svc.record(
                AuditEntryCreate(
                    tenant_id="acme",
                    action=action,
                    resource_type=action.split(".")[0],
                    resource_id="r-1",
                    summary=action,
                )
            )
        assert session.commit.await_count == 3


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


class TestRetrieval:
    async def test_get_returns_entry(self) -> None:
        e = _make_entry()
        session = _scalar_session(e)
        svc = AuditService(session)  # type: ignore[arg-type]
        result = await svc.get(e.id)
        assert result is e

    async def test_get_missing_raises_not_found(self) -> None:
        session = _scalar_session(None)
        svc = AuditService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.get(uuid4())

    async def test_list_returns_entries_for_tenant(self) -> None:
        entries = [_make_entry() for _ in range(8)]
        session = _scalars_session(entries)
        svc = AuditService(session)  # type: ignore[arg-type]
        result = await svc.list_for_tenant("acme")
        assert len(result) == 8

    async def test_list_empty_tenant_returns_empty(self) -> None:
        session = _scalars_session([])
        svc = AuditService(session)  # type: ignore[arg-type]
        result = await svc.list_for_tenant("no-such-tenant")
        assert result == []


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


class TestFiltering:
    async def test_filter_by_action(self) -> None:
        entries = [_make_entry(action="user.create") for _ in range(3)]
        session = _scalars_session(entries)
        svc = AuditService(session)  # type: ignore[arg-type]
        result = await svc.list_for_tenant("acme", action="user.create")
        assert all(e.action == "user.create" for e in result)

    async def test_filter_by_resource_type(self) -> None:
        entries = [_make_entry(resource_type="policy") for _ in range(2)]
        session = _scalars_session(entries)
        svc = AuditService(session)  # type: ignore[arg-type]
        result = await svc.list_for_tenant("acme", resource_type="policy")
        assert all(e.resource_type == "policy" for e in result)

    async def test_count_for_tenant(self) -> None:
        count_result = MagicMock()
        count_result.scalar_one.return_value = 15
        session = _scalar_session(None)
        session.execute = AsyncMock(return_value=count_result)
        svc = AuditService(session)  # type: ignore[arg-type]
        count = await svc.count_for_tenant("acme")
        assert count == 15

    async def test_count_returns_zero_for_empty(self) -> None:
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        session = _scalar_session(None)
        session.execute = AsyncMock(return_value=count_result)
        svc = AuditService(session)  # type: ignore[arg-type]
        count = await svc.count_for_tenant("ghost")
        assert count == 0


# ---------------------------------------------------------------------------
# Append-only semantics
# ---------------------------------------------------------------------------


class TestAppendOnly:
    async def test_no_update_method_on_service(self) -> None:
        session = _scalar_session(None)
        svc = AuditService(session)  # type: ignore[arg-type]
        assert not hasattr(svc, "update")

    async def test_no_delete_method_on_service(self) -> None:
        session = _scalar_session(None)
        svc = AuditService(session)  # type: ignore[arg-type]
        assert not hasattr(svc, "delete")

    async def test_no_deactivate_method_on_service(self) -> None:
        session = _scalar_session(None)
        svc = AuditService(session)  # type: ignore[arg-type]
        assert not hasattr(svc, "deactivate")

    async def test_entry_has_no_updated_at(self) -> None:
        e = _make_entry()
        assert not hasattr(e, "updated_at")

    async def test_record_assigns_id_at_construction(self) -> None:
        session = _scalar_session(None)
        svc = AuditService(session)  # type: ignore[arg-type]
        create = AuditEntryCreate(
            tenant_id="t",
            action="user.create",
            resource_type="user",
            resource_id="u-1",
            summary="test",
        )
        entry = await svc.record(create)
        assert entry.id is not None
        assert entry.tenant_id == "t"
        assert entry.action == "user.create"
