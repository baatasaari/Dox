"""Module 2 — Adapters: Metrics tests."""
from __future__ import annotations

import pytest

from common.adapters.metrics import InMemoryMetricsAdapter, NoopMetricsAdapter


class TestNoopMetricsAdapter:
    def test_increment_does_not_raise(self) -> None:
        NoopMetricsAdapter().increment("requests", 1, {"env": "test"})

    def test_gauge_does_not_raise(self) -> None:
        NoopMetricsAdapter().gauge("memory_mb", 512.0)

    def test_histogram_does_not_raise(self) -> None:
        NoopMetricsAdapter().histogram("latency_ms", 42.5, {"route": "/health"})

    def test_close_does_not_raise(self) -> None:
        NoopMetricsAdapter().close()

    def test_increment_default_value_is_one(self) -> None:
        NoopMetricsAdapter().increment("x")


class TestInMemoryMetricsAdapter:
    @pytest.fixture()
    def adapter(self) -> InMemoryMetricsAdapter:
        return InMemoryMetricsAdapter()

    def test_increment_stores_value(self, adapter: InMemoryMetricsAdapter) -> None:
        adapter.increment("hits")
        assert adapter.get_counter("hits") == 1

    def test_increment_accumulates(self, adapter: InMemoryMetricsAdapter) -> None:
        adapter.increment("hits")
        adapter.increment("hits")
        assert adapter.get_counter("hits") == 2

    def test_increment_with_explicit_value(self, adapter: InMemoryMetricsAdapter) -> None:
        adapter.increment("bytes", 100)
        adapter.increment("bytes", 200)
        assert adapter.get_counter("bytes") == 300

    def test_unknown_counter_returns_zero(self, adapter: InMemoryMetricsAdapter) -> None:
        assert adapter.get_counter("never_incremented") == 0

    def test_gauge_stores_value(self, adapter: InMemoryMetricsAdapter) -> None:
        adapter.gauge("queue_size", 10.0)
        assert adapter.get_gauge("queue_size") == 10.0

    def test_gauge_stores_latest_value(self, adapter: InMemoryMetricsAdapter) -> None:
        adapter.gauge("q", 10.0)
        adapter.gauge("q", 5.0)
        assert adapter.get_gauge("q") == 5.0

    def test_unknown_gauge_returns_none(self, adapter: InMemoryMetricsAdapter) -> None:
        assert adapter.get_gauge("unset") is None

    def test_histogram_collects_all_values(self, adapter: InMemoryMetricsAdapter) -> None:
        adapter.histogram("latency", 10.0)
        adapter.histogram("latency", 20.0)
        adapter.histogram("latency", 15.0)
        assert adapter.get_histogram("latency") == [10.0, 20.0, 15.0]

    def test_unknown_histogram_returns_empty_list(
        self, adapter: InMemoryMetricsAdapter
    ) -> None:
        assert adapter.get_histogram("unset") == []

    def test_get_histogram_returns_copy(self, adapter: InMemoryMetricsAdapter) -> None:
        adapter.histogram("h", 1.0)
        result = adapter.get_histogram("h")
        result.append(999.0)
        assert adapter.get_histogram("h") == [1.0]

    def test_clear_resets_all_metrics(self, adapter: InMemoryMetricsAdapter) -> None:
        adapter.increment("c")
        adapter.gauge("g", 1.0)
        adapter.histogram("h", 2.0)
        adapter.clear()
        assert adapter.get_counter("c") == 0
        assert adapter.get_gauge("g") is None
        assert adapter.get_histogram("h") == []

    def test_close_is_safe(self, adapter: InMemoryMetricsAdapter) -> None:
        adapter.close()
