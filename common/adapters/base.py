"""Abstract base classes for all pluggable infrastructure adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class EventBusAdapter(ABC):
    """Publish events to a topic-based message bus."""

    @abstractmethod
    async def publish(self, topic: str, event: dict[str, Any]) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


class ObjectStoreAdapter(ABC):
    """Store and retrieve binary objects by key."""

    @abstractmethod
    async def put(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None: ...

    @abstractmethod
    async def get(self, key: str) -> bytes: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abstractmethod
    async def close(self) -> None: ...


class SecretStoreAdapter(ABC):
    """Retrieve secrets by name from a backing store."""

    @abstractmethod
    async def get_secret(self, name: str) -> str: ...

    @abstractmethod
    async def close(self) -> None: ...


class MetricsAdapter(ABC):
    """Emit application metrics (counters, gauges, histograms).

    Methods are synchronous so they can be called from anywhere without await.
    """

    @abstractmethod
    def increment(
        self, name: str, value: int = 1, tags: dict[str, str] | None = None
    ) -> None: ...

    @abstractmethod
    def gauge(
        self, name: str, value: float, tags: dict[str, str] | None = None
    ) -> None: ...

    @abstractmethod
    def histogram(
        self, name: str, value: float, tags: dict[str, str] | None = None
    ) -> None: ...

    @abstractmethod
    def close(self) -> None: ...
