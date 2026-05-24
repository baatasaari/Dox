"""Metrics adapter implementations."""
from __future__ import annotations

from collections import defaultdict

from .base import MetricsAdapter


class NoopMetricsAdapter(MetricsAdapter):
    """Discards all metrics. Used when no metrics backend is configured."""

    def increment(
        self, name: str, value: int = 1, tags: dict[str, str] | None = None
    ) -> None:
        pass

    def gauge(
        self, name: str, value: float, tags: dict[str, str] | None = None
    ) -> None:
        pass

    def histogram(
        self, name: str, value: float, tags: dict[str, str] | None = None
    ) -> None:
        pass

    def close(self) -> None:
        pass


class InMemoryMetricsAdapter(MetricsAdapter):
    """Collects metrics in memory. For testing and local dev.

    Tags are accepted but not indexed — all values aggregate by metric name only.
    """

    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)

    def increment(
        self, name: str, value: int = 1, tags: dict[str, str] | None = None
    ) -> None:
        self._counters[name] += value

    def gauge(
        self, name: str, value: float, tags: dict[str, str] | None = None
    ) -> None:
        self._gauges[name] = value

    def histogram(
        self, name: str, value: float, tags: dict[str, str] | None = None
    ) -> None:
        self._histograms[name].append(value)

    def get_counter(self, name: str) -> int:
        return self._counters[name]

    def get_gauge(self, name: str) -> float | None:
        return self._gauges.get(name)

    def get_histogram(self, name: str) -> list[float]:
        return list(self._histograms[name])

    def clear(self) -> None:
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()

    def close(self) -> None:
        pass
