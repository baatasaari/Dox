"""Infrastructure adapter framework — plug-and-play cloud-agnostic backends."""
from __future__ import annotations

from .base import EventBusAdapter, MetricsAdapter, ObjectStoreAdapter, SecretStoreAdapter
from .event_bus import InMemoryEventBusAdapter, RedisStreamsEventBusAdapter
from .metrics import InMemoryMetricsAdapter, NoopMetricsAdapter
from .object_store import InMemoryObjectStoreAdapter, LocalFsObjectStoreAdapter
from .registry import AdapterRegistry
from .secret_store import EnvSecretStoreAdapter, InMemorySecretStoreAdapter

__all__ = [
    "AdapterRegistry",
    "EnvSecretStoreAdapter",
    "EventBusAdapter",
    "InMemoryEventBusAdapter",
    "InMemoryMetricsAdapter",
    "InMemoryObjectStoreAdapter",
    "InMemorySecretStoreAdapter",
    "LocalFsObjectStoreAdapter",
    "MetricsAdapter",
    "NoopMetricsAdapter",
    "ObjectStoreAdapter",
    "RedisStreamsEventBusAdapter",
    "SecretStoreAdapter",
]
