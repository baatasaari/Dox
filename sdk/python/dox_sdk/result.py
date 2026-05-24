"""Result types returned by DoxClient emit methods."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID


@dataclass
class EmitResult:
    """Result of a single-event emit call."""

    success: bool
    event_id: UUID | None = None
    status_code: int | None = None
    error: str | None = None
    emitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class BatchEmitResult:
    """Result of a batch emit call."""

    success: bool
    accepted: int = 0
    event_ids: list[UUID] = field(default_factory=list)
    status_code: int | None = None
    error: str | None = None
    emitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
