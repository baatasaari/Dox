from __future__ import annotations

import hashlib
import json
from typing import Any

from common.schemas.enums import (
    _SCHEMA_VERSION_RE,
    _SHA256_RE,
    _TRACEPARENT_RE,
)


def validate_sha256_hash(value: str | None) -> str | None:
    """Accept None or a 64-character lowercase hexadecimal SHA-256 string."""
    if value is None:
        return None
    if not _SHA256_RE.match(value):
        raise ValueError(
            f"must be a 64-character lowercase hexadecimal string, got {len(value)} chars"
        )
    return value


def validate_traceparent(value: str | None) -> str | None:
    """Accept None or a W3C traceparent header (format: 00-{32hex}-{16hex}-{2hex})."""
    if value is None:
        return None
    if not _TRACEPARENT_RE.match(value):
        raise ValueError(
            "must be a valid W3C traceparent header in format 00-{32hex}-{16hex}-{2hex}"
        )
    return value


def validate_schema_version(value: str) -> str:
    """Accept a MAJOR.MINOR version string (e.g. '1.0', '2.10')."""
    if not _SCHEMA_VERSION_RE.match(value):
        raise ValueError(
            f"schema_version must be in MAJOR.MINOR format (e.g. '1.0'), got '{value}'"
        )
    return value


# Alias used in events.py field validators
validate_payload_hash = validate_sha256_hash


def compute_payload_hash(payload: dict[str, Any]) -> str:
    """Return a deterministic SHA-256 hex digest of the payload.

    Keys are sorted before serialisation so insertion order does not affect the hash.
    """
    serialised = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()
