"""Pydantic schemas for session playback."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


class SessionReplayCreate(BaseModel):
    """Request body for creating a new replay of an existing session."""

    tenant_id: str = Field(min_length=1, max_length=255)
    original_session_id: str = Field(min_length=1, max_length=255)
    # If omitted, inferred from the first event of the session.
    agent_id: str | None = Field(default=None, max_length=255)
    # Human-readable label; defaults to "Replay of <session_id>".
    name: str | None = Field(default=None, max_length=500)
    # 0.0 = manual step-through; 1.0 = realtime; 2.0 = 2× speed.
    speed_factor: float = Field(default=0.0, ge=0.0, le=100.0)


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


class ReplayFrame(BaseModel):
    """One ordered step in a session replay."""

    sequence_num: int
    event_id: str
    event_type: str
    timestamp: datetime
    elapsed_seconds: float
    # Key fields extracted from the payload — not the full blob.
    payload_summary: dict[str, Any]


class AccumulatedState(BaseModel):
    """Agent state reconstructed by folding over the event stream up to *position*.

    This captures what the agent "knew" and what had happened at a given point:

    * ``context_window``   — the most recent events (sliding window, ≤ 20).
    * ``memory``           — approved memory writes not subsequently rolled back.
    * ``active_tool_calls``— tool calls started but not yet completed/failed.
    * ``sentinel_alerts``  — all alerts triggered up to this position.
    * ``interventions``    — all intervention_applied events up to this position.
    * ``event_type_counts``— histogram of all event types seen so far.
    * ``current_agent_step``— 0-based step index (agent_step_started - agent_step_completed).
    """

    position: int
    total_events: int
    context_window: list[dict[str, Any]]
    memory: list[dict[str, Any]]
    active_tool_calls: list[str]
    sentinel_alerts: list[str]
    interventions: list[str]
    event_type_counts: dict[str, int]
    current_agent_step: int


class SessionReplayResponse(BaseModel):
    """Full representation of a persisted SessionReplay."""

    id: UUID
    tenant_id: str
    original_session_id: str
    agent_id: str
    name: str
    status: str
    total_events: int
    current_position: int
    speed_factor: float
    original_started_at: datetime | None
    original_ended_at: datetime | None
    original_duration_seconds: float | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReplayListResponse(BaseModel):
    replays: list[SessionReplayResponse]
    total: int


class ReplayFrameListResponse(BaseModel):
    replay_id: UUID
    frames: list[ReplayFrame]
    total: int
