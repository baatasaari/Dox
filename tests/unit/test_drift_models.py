"""Module 7 — Drift: model tests."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from common.models.baseline import AgentBaseline


def _make_baseline(**kw: object) -> AgentBaseline:
    defaults = dict(
        id=uuid4(),
        tenant_id="tenant-acme",
        agent_id="agent-1",
        lookback_hours=24,
        event_counts={"agent_started": 10, "tool_call_started": 5},
        total_events=15,
        computed_at=datetime.now(UTC),
    )
    defaults.update(kw)
    return AgentBaseline(**defaults)


class TestAgentBaselineDefaults:
    def test_is_active_defaults_to_true(self) -> None:
        b = _make_baseline()
        assert b.is_active is True

    def test_explicit_is_active_false(self) -> None:
        b = _make_baseline(is_active=False)
        assert b.is_active is False

    def test_event_counts_defaults_to_empty(self) -> None:
        b = AgentBaseline(
            id=uuid4(),
            tenant_id="t",
            agent_id="a",
            lookback_hours=1,
            total_events=0,
            computed_at=datetime.now(UTC),
        )
        assert b.event_counts == {}

    def test_explicit_event_counts_preserved(self) -> None:
        counts = {"agent_started": 3}
        b = _make_baseline(event_counts=counts)
        assert b.event_counts == counts


class TestAgentBaselineFields:
    def test_all_required_fields_set(self) -> None:
        b = _make_baseline()
        assert b.tenant_id == "tenant-acme"
        assert b.agent_id == "agent-1"
        assert b.lookback_hours == 24
        assert b.total_events == 15

    def test_id_is_uuid(self) -> None:
        b = _make_baseline()
        import uuid
        assert isinstance(b.id, uuid.UUID)

    def test_computed_at_preserved(self) -> None:
        now = datetime.now(UTC)
        b = _make_baseline(computed_at=now)
        assert b.computed_at == now
