"""SHA-256 hash-chain verification for persisted EventRecords."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from common.models.event import EventRecord
from common.schemas.validators import compute_payload_hash


class IntegrityStatus(StrEnum):
    ok = "ok"
    hash_mismatch = "hash_mismatch"
    missing_hash = "missing_hash"


@dataclass
class RecordIntegrity:
    record_id: str
    event_id: str
    status: IntegrityStatus
    stored_hash: str | None
    computed_hash: str


@dataclass
class IntegrityReport:
    tenant_id: str
    total_checked: int
    passed: int
    failed: int
    records: list[RecordIntegrity] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return self.failed == 0


def check_record(record: EventRecord) -> RecordIntegrity:
    """Verify the stored payload_hash matches the payload's computed hash."""
    computed = compute_payload_hash(record.payload)
    stored = record.payload_hash

    if stored is None:
        status = IntegrityStatus.missing_hash
    elif stored == computed:
        status = IntegrityStatus.ok
    else:
        status = IntegrityStatus.hash_mismatch

    return RecordIntegrity(
        record_id=str(record.id),
        event_id=str(record.event_id),
        status=status,
        stored_hash=stored,
        computed_hash=computed,
    )


def verify_tenant_integrity(records: list[EventRecord]) -> IntegrityReport:
    """Check every record in *records* and return an aggregate IntegrityReport.

    All records must belong to the same tenant; the tenant_id is taken from the
    first record (or empty string if the list is empty).
    """
    tenant_id = records[0].tenant_id if records else ""
    checked: list[RecordIntegrity] = [check_record(r) for r in records]
    passed = sum(1 for c in checked if c.status == IntegrityStatus.ok)
    failed = len(checked) - passed
    return IntegrityReport(
        tenant_id=tenant_id,
        total_checked=len(checked),
        passed=passed,
        failed=failed,
        records=checked,
    )
