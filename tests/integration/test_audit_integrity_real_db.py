"""Module E — Audit trail integrity via real PostgreSQL.

What this proves
----------------
1. A freshly-inserted EventRecord with the correct ``payload_hash`` passes
   ``verify_tenant_integrity``.

2. A payload mutated via ORM UPDATE (without touching ``payload_hash``) is
   flagged as ``hash_mismatch`` after ``session.refresh`` expires the ORM cache.

3. In a mixed batch, only tampered records fail; clean siblings pass.

4. Ten concurrent ``AuditService.record()`` calls — each in its own session —
   all persist; the final count equals exactly 10.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from common.audit.integrity import IntegrityStatus, verify_tenant_integrity
from common.models.audit_log import AuditEntry
from common.models.event import EventRecord
from common.schemas.audit_log import AuditEntryCreate
from common.schemas.validators import compute_payload_hash
from services.audit.service import AuditService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    return uuid4().hex[:8]


def _make_event_record(tenant_id: str, payload: dict | None = None) -> EventRecord:
    now = datetime.now(UTC)
    p = payload or {"tool": "search", "query": _uid()}
    return EventRecord(
        event_id=uuid4(),
        trace_id=uuid4(),
        session_id=f"sess-{_uid()}",
        tenant_id=tenant_id,
        agent_id=f"agent-{_uid()}",
        agent_version="1.0",
        event_type="tool_call",
        environment="test",
        timestamp=now,
        client_timestamp=now,
        schema_version="1.0",
        payload=p,
        raw_event={},
        payload_hash=compute_payload_hash(p),
    )


# ---------------------------------------------------------------------------
# EventRecord integrity (uses db_session — rolled back automatically)
# ---------------------------------------------------------------------------


class TestEventRecordIntegrity:
    """SHA-256 payload integrity check on real persisted EventRecords."""

    async def test_clean_record_passes_integrity_check(
        self, db_session: AsyncSession
    ) -> None:
        record = _make_event_record("tenant-integrity-a")
        db_session.add(record)
        await db_session.flush()

        report = verify_tenant_integrity([record])

        assert report.is_clean
        assert report.passed == 1
        assert report.failed == 0

    async def test_tampered_payload_detected(
        self, db_session: AsyncSession
    ) -> None:
        """Payload mutated without updating hash is flagged as hash_mismatch."""
        record = _make_event_record("tenant-integrity-b")
        db_session.add(record)
        await db_session.flush()

        # Corrupt the payload via an ORM UPDATE — payload_hash is NOT updated.
        await db_session.execute(
            update(EventRecord)
            .where(EventRecord.id == record.id)
            .values(payload={"tampered": True})
        )
        # Expire the identity-map cache so the next read fetches from the DB.
        await db_session.refresh(record)

        report = verify_tenant_integrity([record])

        assert not report.is_clean
        assert report.failed == 1
        assert report.records[0].status == IntegrityStatus.hash_mismatch

    async def test_only_tampered_records_fail_clean_siblings_pass(
        self, db_session: AsyncSession
    ) -> None:
        """Integrity check isolates failures to tampered records only."""
        tenant = f"tenant-integrity-{_uid()}"
        records = [_make_event_record(tenant) for _ in range(4)]
        for r in records:
            db_session.add(r)
        await db_session.flush()

        # Tamper the last two records; leave the first two clean.
        for r in records[2:]:
            await db_session.execute(
                update(EventRecord)
                .where(EventRecord.id == r.id)
                .values(payload={"tampered": True})
            )
        for r in records[2:]:
            await db_session.refresh(r)

        report = verify_tenant_integrity(records)

        assert report.total_checked == 4
        assert report.passed == 2
        assert report.failed == 2
        statuses = {ri.status for ri in report.records}
        assert IntegrityStatus.ok in statuses
        assert IntegrityStatus.hash_mismatch in statuses


# ---------------------------------------------------------------------------
# Concurrent AuditEntry writes (uses real_engine — real commits, own cleanup)
# ---------------------------------------------------------------------------


class TestConcurrentAuditEntryWrites:
    """Separate sessions inserting AuditEntry rows concurrently all persist."""

    async def test_ten_concurrent_audit_writes_all_persist(
        self, real_engine: AsyncEngine
    ) -> None:
        tenant = f"audit-conc-{_uid()}"

        async def _write(i: int) -> None:
            async with AsyncSession(real_engine) as sess:
                await AuditService(sess).record(
                    AuditEntryCreate(
                        tenant_id=tenant,
                        action="agent.registered",
                        resource_type="agent",
                        resource_id=f"agent-{i}",
                        summary=f"Registered agent {i}",
                    )
                )

        try:
            await asyncio.gather(*[_write(i) for i in range(10)])

            async with AsyncSession(real_engine) as sess:
                count = await AuditService(sess).count_for_tenant(tenant)

            assert count == 10, f"Expected 10 audit entries, found {count}"
        finally:
            async with AsyncSession(real_engine) as sess:
                async with sess.begin():
                    await sess.execute(
                        delete(AuditEntry).where(AuditEntry.tenant_id == tenant)
                    )
