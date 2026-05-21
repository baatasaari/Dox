"""Module 6 — Audit integrity tests."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from common.audit.integrity import (
    IntegrityReport,
    IntegrityStatus,
    check_record,
    verify_tenant_integrity,
)
from common.models.event import EventRecord
from common.schemas.validators import compute_payload_hash


def _make_record(
    payload: dict | None = None,
    payload_hash: str | None = None,
    tenant_id: str = "tenant-acme",
) -> EventRecord:
    p = payload or {"step": "test"}
    return EventRecord(
        id=uuid4(),
        event_id=uuid4(),
        trace_id=uuid4(),
        session_id="sess-1",
        tenant_id=tenant_id,
        agent_id="agent-1",
        agent_version="1.0.0",
        event_type="agent_started",
        environment="dev",
        timestamp=datetime.now(UTC),
        client_timestamp=datetime.now(UTC),
        schema_version="1.0",
        payload=p,
        raw_event={},
        payload_hash=payload_hash if payload_hash is not None else compute_payload_hash(p),
    )


class TestCheckRecord:
    def test_valid_hash_returns_ok(self) -> None:
        record = _make_record()
        result = check_record(record)
        assert result.status == IntegrityStatus.ok

    def test_tampered_hash_returns_mismatch(self) -> None:
        record = _make_record(payload_hash="a" * 64)
        result = check_record(record)
        assert result.status == IntegrityStatus.hash_mismatch

    def test_missing_hash_returns_missing_hash(self) -> None:
        record = _make_record()
        record.payload_hash = None
        result = check_record(record)
        assert result.status == IntegrityStatus.missing_hash

    def test_result_contains_record_id(self) -> None:
        record = _make_record()
        result = check_record(record)
        assert result.record_id == str(record.id)

    def test_result_contains_event_id(self) -> None:
        record = _make_record()
        result = check_record(record)
        assert result.event_id == str(record.event_id)

    def test_computed_hash_is_deterministic(self) -> None:
        payload = {"key": "value", "num": 42}
        record = _make_record(payload=payload, payload_hash=compute_payload_hash(payload))
        result = check_record(record)
        assert result.status == IntegrityStatus.ok
        assert result.computed_hash == compute_payload_hash(payload)

    def test_stored_hash_preserved_in_result(self) -> None:
        record = _make_record()
        stored = record.payload_hash
        result = check_record(record)
        assert result.stored_hash == stored


class TestVerifyTenantIntegrity:
    def test_all_valid_records_is_clean(self) -> None:
        records = [_make_record() for _ in range(5)]
        report = verify_tenant_integrity(records)
        assert report.is_clean is True
        assert report.failed == 0
        assert report.passed == 5

    def test_one_tampered_record_not_clean(self) -> None:
        records = [_make_record() for _ in range(3)]
        records[1].payload_hash = "b" * 64
        report = verify_tenant_integrity(records)
        assert report.is_clean is False
        assert report.failed == 1
        assert report.passed == 2

    def test_total_checked_matches_input(self) -> None:
        records = [_make_record() for _ in range(7)]
        report = verify_tenant_integrity(records)
        assert report.total_checked == 7

    def test_empty_list_returns_clean_report(self) -> None:
        report = verify_tenant_integrity([])
        assert report.is_clean is True
        assert report.total_checked == 0
        assert report.tenant_id == ""

    def test_tenant_id_taken_from_first_record(self) -> None:
        records = [_make_record(tenant_id="tenant-xyz") for _ in range(2)]
        report = verify_tenant_integrity(records)
        assert report.tenant_id == "tenant-xyz"

    def test_report_has_record_per_input(self) -> None:
        records = [_make_record() for _ in range(4)]
        report = verify_tenant_integrity(records)
        assert len(report.records) == 4

    def test_missing_hash_counted_as_failed(self) -> None:
        records = [_make_record() for _ in range(3)]
        records[0].payload_hash = None
        report = verify_tenant_integrity(records)
        assert report.failed == 1


class TestIntegrityReport:
    def test_is_clean_false_when_failed_gt_zero(self) -> None:
        report = IntegrityReport(
            tenant_id="t",
            total_checked=2,
            passed=1,
            failed=1,
        )
        assert report.is_clean is False

    def test_is_clean_true_when_zero_failed(self) -> None:
        report = IntegrityReport(
            tenant_id="t",
            total_checked=3,
            passed=3,
            failed=0,
        )
        assert report.is_clean is True
