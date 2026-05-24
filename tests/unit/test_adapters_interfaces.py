"""Module 2 — Adapters: Abstract interface contract tests."""
from __future__ import annotations

import pytest

from common.adapters.base import (
    EventBusAdapter,
    MetricsAdapter,
    ObjectStoreAdapter,
    SecretStoreAdapter,
)
from common.adapters.event_bus import InMemoryEventBusAdapter, RedisStreamsEventBusAdapter
from common.adapters.metrics import InMemoryMetricsAdapter, NoopMetricsAdapter
from common.adapters.object_store import InMemoryObjectStoreAdapter, LocalFsObjectStoreAdapter
from common.adapters.secret_store import EnvSecretStoreAdapter, InMemorySecretStoreAdapter


class TestAbstractBases:
    def test_event_bus_adapter_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            EventBusAdapter()  # type: ignore[abstract]

    def test_object_store_adapter_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            ObjectStoreAdapter()  # type: ignore[abstract]

    def test_secret_store_adapter_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            SecretStoreAdapter()  # type: ignore[abstract]

    def test_metrics_adapter_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            MetricsAdapter()  # type: ignore[abstract]


class TestEventBusSubclasses:
    def test_in_memory_is_event_bus_adapter(self) -> None:
        assert issubclass(InMemoryEventBusAdapter, EventBusAdapter)

    def test_redis_streams_is_event_bus_adapter(self) -> None:
        assert issubclass(RedisStreamsEventBusAdapter, EventBusAdapter)

    def test_in_memory_instance_passes_isinstance_check(self) -> None:
        assert isinstance(InMemoryEventBusAdapter(), EventBusAdapter)


class TestObjectStoreSubclasses:
    def test_in_memory_is_object_store_adapter(self) -> None:
        assert issubclass(InMemoryObjectStoreAdapter, ObjectStoreAdapter)

    def test_local_fs_is_object_store_adapter(self) -> None:
        assert issubclass(LocalFsObjectStoreAdapter, ObjectStoreAdapter)

    def test_in_memory_instance_passes_isinstance_check(self) -> None:
        assert isinstance(InMemoryObjectStoreAdapter(), ObjectStoreAdapter)


class TestSecretStoreSubclasses:
    def test_env_is_secret_store_adapter(self) -> None:
        assert issubclass(EnvSecretStoreAdapter, SecretStoreAdapter)

    def test_in_memory_is_secret_store_adapter(self) -> None:
        assert issubclass(InMemorySecretStoreAdapter, SecretStoreAdapter)


class TestMetricsSubclasses:
    def test_noop_is_metrics_adapter(self) -> None:
        assert issubclass(NoopMetricsAdapter, MetricsAdapter)

    def test_in_memory_is_metrics_adapter(self) -> None:
        assert issubclass(InMemoryMetricsAdapter, MetricsAdapter)
