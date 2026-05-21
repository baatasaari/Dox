from __future__ import annotations

import re
from enum import Enum


class Environment(str, Enum):
    dev = "dev"
    test = "test"
    staging = "staging"
    prod = "prod"


class EventType(str, Enum):
    user_input_received = "user_input_received"
    agent_started = "agent_started"
    agent_step_started = "agent_step_started"
    agent_step_completed = "agent_step_completed"
    model_called = "model_called"
    model_response_received = "model_response_received"
    reasoning_captured = "reasoning_captured"
    tool_selected = "tool_selected"
    tool_call_started = "tool_call_started"
    tool_call_completed = "tool_call_completed"
    tool_call_failed = "tool_call_failed"
    tool_call_blocked = "tool_call_blocked"
    memory_read = "memory_read"
    memory_write_requested = "memory_write_requested"
    memory_write_approved = "memory_write_approved"
    memory_write_blocked = "memory_write_blocked"
    memory_rollback = "memory_rollback"
    rag_query = "rag_query"
    rag_chunk_retrieved = "rag_chunk_retrieved"
    policy_evaluated = "policy_evaluated"
    policy_failed = "policy_failed"
    sentinel_alert_created = "sentinel_alert_created"
    intervention_requested = "intervention_requested"
    intervention_applied = "intervention_applied"
    delegation_started = "delegation_started"
    delegation_completed = "delegation_completed"
    consent_checked = "consent_checked"
    agent_completed = "agent_completed"
    agent_failed = "agent_failed"
    agent_paused = "agent_paused"
    agent_resumed = "agent_resumed"
    agent_terminated = "agent_terminated"
    replay_started = "replay_started"
    replay_completed = "replay_completed"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class SentinelType(str, Enum):
    trajectory = "trajectory"
    tool_misuse = "tool_misuse"
    policy_breach = "policy_breach"
    memory = "memory"
    drift = "drift"
    injection = "injection"
    cost_loop = "cost_loop"
    delegation = "delegation"
    bias = "bias"
    hallucination = "hallucination"
    regulatory = "regulatory"


class InterventionAction(str, Enum):
    allow = "allow"
    warn = "warn"
    redact = "redact"
    block_tool_call = "block_tool_call"
    pause_agent = "pause_agent"
    request_human_review = "request_human_review"
    force_safe_response = "force_safe_response"
    rollback_memory_write = "rollback_memory_write"
    isolate_agent = "isolate_agent"
    terminate_execution = "terminate_execution"


_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_TRACEPARENT_RE = re.compile(r"^00-[a-f0-9]{32}-[a-f0-9]{16}-[a-f0-9]{2}$")
_SCHEMA_VERSION_RE = re.compile(r"^\d+\.\d+$")
