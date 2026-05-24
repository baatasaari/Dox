"""Module 2 — Adapters: Event bus tests."""
from __future__ import annotations

import pytest

from common.adapters.event_bus import InMemoryEventBusAdapter


@pytest.fixture()
def adapter() -> InMemoryEventBusAdapter:
    return InMemoryEventBusAdapter()


class TestInMemoryEventBusAdapter:
    async def test_publish_stores_event_for_topic(
        self, adapter: InMemoryEventBusAdapter
    ) -> None:
        await adapter.publish("events", {"id": "1"})
        assert len(adapter.get_events("events")) == 1

    async def test_published_event_is_deep_copied(
        self, adapter: InMemoryEventBusAdapter
    ) -> None:
        event: dict[str, list[int]] = {"data": [1, 2, 3]}
        await adapter.publish("t", event)
        event["data"].append(4)
        stored = adapter.get_events("t")[0]
        assert stored["data"] == [1, 2, 3]

    async def test_events_returned_in_publish_order(
        self, adapter: InMemoryEventBusAdapter
    ) -> None:
        for i in range(5):
            await adapter.publish("seq", {"n": i})
        events = adapter.get_events("seq")
        assert [e["n"] for e in events] == [0, 1, 2, 3, 4]

    async def test_multiple_topics_are_independent(
        self, adapter: InMemoryEventBusAdapter
    ) -> None:
        await adapter.publish("a", {"x": 1})
        await adapter.publish("b", {"x": 2})
        assert len(adapter.get_events("a")) == 1
        assert len(adapter.get_events("b")) == 1
        assert adapter.get_events("a")[0] == {"x": 1}

    def test_get_events_for_unknown_topic_returns_empty(
        self, adapter: InMemoryEventBusAdapter
    ) -> None:
        assert adapter.get_events("ghost") == []

    async def test_clear_removes_all_topics(
        self, adapter: InMemoryEventBusAdapter
    ) -> None:
        await adapter.publish("x", {"v": 1})
        await adapter.publish("y", {"v": 2})
        adapter.clear()
        assert adapter.get_events("x") == []
        assert adapter.get_events("y") == []

    async def test_publish_empty_dict_is_accepted(
        self, adapter: InMemoryEventBusAdapter
    ) -> None:
        await adapter.publish("t", {})
        assert adapter.get_events("t") == [{}]

    async def test_close_is_idempotent(self, adapter: InMemoryEventBusAdapter) -> None:
        await adapter.close()
        await adapter.close()

    async def test_get_events_returns_copy_not_internal_list(
        self, adapter: InMemoryEventBusAdapter
    ) -> None:
        await adapter.publish("t", {"a": 1})
        result = adapter.get_events("t")
        result.clear()
        assert len(adapter.get_events("t")) == 1

    async def test_publish_to_same_topic_accumulates(
        self, adapter: InMemoryEventBusAdapter
    ) -> None:
        for i in range(3):
            await adapter.publish("t", {"i": i})
        assert len(adapter.get_events("t")) == 3
