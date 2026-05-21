"""Module 2 — Adapters: AdapterRegistry tests."""
from __future__ import annotations

import pytest

from common.adapters.event_bus import InMemoryEventBusAdapter
from common.adapters.metrics import InMemoryMetricsAdapter, NoopMetricsAdapter
from common.adapters.object_store import InMemoryObjectStoreAdapter, LocalFsObjectStoreAdapter
from common.adapters.registry import AdapterRegistry
from common.adapters.secret_store import EnvSecretStoreAdapter, InMemorySecretStoreAdapter
from common.config import AdapterSettings, DatabaseSettings, Settings
from common.exceptions import ConfigurationError


def _make_settings(**overrides: str) -> Settings:
    adapters = AdapterSettings(**overrides)
    return Settings(
        database=DatabaseSettings(url="postgresql+asyncpg://test:test@localhost/test"),
        adapters=adapters,
    )


class TestAdapterRegistryEventBus:
    def test_in_memory_event_bus_created(self) -> None:
        registry = AdapterRegistry(_make_settings(event_bus="in_memory"))
        assert isinstance(registry.event_bus, InMemoryEventBusAdapter)

    def test_unknown_event_bus_raises_configuration_error(self) -> None:
        with pytest.raises(ConfigurationError, match="event_bus"):
            AdapterRegistry(_make_settings(event_bus="kafka"))

    def test_event_bus_same_instance_on_repeated_access(self) -> None:
        registry = AdapterRegistry(_make_settings(event_bus="in_memory"))
        assert registry.event_bus is registry.event_bus


class TestAdapterRegistryObjectStore:
    def test_in_memory_object_store_created(self) -> None:
        registry = AdapterRegistry(_make_settings(object_store="in_memory"))
        assert isinstance(registry.object_store, InMemoryObjectStoreAdapter)

    def test_local_fs_object_store_created(self, tmp_path: pytest.TempPathFactory) -> None:
        settings = Settings(
            database=DatabaseSettings(url="postgresql+asyncpg://test:test@localhost/test"),
            adapters=AdapterSettings(object_store="local_fs", local_fs_path=str(tmp_path)),
        )
        registry = AdapterRegistry(settings)
        assert isinstance(registry.object_store, LocalFsObjectStoreAdapter)

    def test_unknown_object_store_raises_configuration_error(self) -> None:
        with pytest.raises(ConfigurationError, match="object_store"):
            AdapterRegistry(_make_settings(object_store="s3"))


class TestAdapterRegistrySecretStore:
    def test_env_secret_store_created(self) -> None:
        registry = AdapterRegistry(_make_settings(secret_store="env"))
        assert isinstance(registry.secret_store, EnvSecretStoreAdapter)

    def test_in_memory_secret_store_created(self) -> None:
        registry = AdapterRegistry(_make_settings(secret_store="in_memory"))
        assert isinstance(registry.secret_store, InMemorySecretStoreAdapter)

    def test_unknown_secret_store_raises_configuration_error(self) -> None:
        with pytest.raises(ConfigurationError, match="secret_store"):
            AdapterRegistry(_make_settings(secret_store="vault"))


class TestAdapterRegistryMetrics:
    def test_noop_metrics_created(self) -> None:
        registry = AdapterRegistry(_make_settings(metrics="noop"))
        assert isinstance(registry.metrics, NoopMetricsAdapter)

    def test_prometheus_maps_to_noop(self) -> None:
        registry = AdapterRegistry(_make_settings(metrics="prometheus"))
        assert isinstance(registry.metrics, NoopMetricsAdapter)

    def test_in_memory_metrics_created(self) -> None:
        registry = AdapterRegistry(_make_settings(metrics="in_memory"))
        assert isinstance(registry.metrics, InMemoryMetricsAdapter)

    def test_unknown_metrics_raises_configuration_error(self) -> None:
        with pytest.raises(ConfigurationError, match="metrics"):
            AdapterRegistry(_make_settings(metrics="datadog"))


class TestAdapterRegistryLifecycle:
    async def test_close_does_not_raise(self) -> None:
        registry = AdapterRegistry(
            _make_settings(
                event_bus="in_memory",
                object_store="in_memory",
                secret_store="in_memory",
                metrics="noop",
            )
        )
        await registry.close()

    async def test_close_is_idempotent(self) -> None:
        registry = AdapterRegistry(_make_settings(event_bus="in_memory"))
        await registry.close()
        await registry.close()
