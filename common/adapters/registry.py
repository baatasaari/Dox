"""AdapterRegistry — constructs and owns the adapter singletons for one process."""
from __future__ import annotations

from common.config import Settings
from common.exceptions import ConfigurationError

from .base import EventBusAdapter, MetricsAdapter, ObjectStoreAdapter, SecretStoreAdapter
from .event_bus import InMemoryEventBusAdapter, RedisStreamsEventBusAdapter
from .metrics import InMemoryMetricsAdapter, NoopMetricsAdapter
from .object_store import InMemoryObjectStoreAdapter, LocalFsObjectStoreAdapter
from .secret_store import EnvSecretStoreAdapter, InMemorySecretStoreAdapter

_KNOWN_EVENT_BUS = {"in_memory", "redis_streams"}
_KNOWN_OBJECT_STORE = {"in_memory", "local_fs"}
_KNOWN_SECRET_STORE = {"in_memory", "env"}
_KNOWN_METRICS = {"in_memory", "noop", "prometheus"}


class AdapterRegistry:
    """Instantiates one adapter per type based on Settings and exposes them as properties.

    Call ``await registry.close()`` during application shutdown.
    """

    def __init__(self, settings: Settings) -> None:
        self._event_bus: EventBusAdapter = self._build_event_bus(settings)
        self._object_store: ObjectStoreAdapter = self._build_object_store(settings)
        self._secret_store: SecretStoreAdapter = self._build_secret_store(settings)
        self._metrics: MetricsAdapter = self._build_metrics(settings)

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @staticmethod
    def _build_event_bus(settings: Settings) -> EventBusAdapter:
        name = settings.adapters.event_bus
        if name not in _KNOWN_EVENT_BUS:
            raise ConfigurationError(
                f"Unknown event_bus adapter '{name}'. "
                f"Valid options: {sorted(_KNOWN_EVENT_BUS)}"
            )
        if name == "redis_streams":
            return RedisStreamsEventBusAdapter(url=settings.redis.url)
        return InMemoryEventBusAdapter()

    @staticmethod
    def _build_object_store(settings: Settings) -> ObjectStoreAdapter:
        name = settings.adapters.object_store
        if name not in _KNOWN_OBJECT_STORE:
            raise ConfigurationError(
                f"Unknown object_store adapter '{name}'. "
                f"Valid options: {sorted(_KNOWN_OBJECT_STORE)}"
            )
        if name == "local_fs":
            return LocalFsObjectStoreAdapter(base_path=settings.adapters.local_fs_path)
        return InMemoryObjectStoreAdapter()

    @staticmethod
    def _build_secret_store(settings: Settings) -> SecretStoreAdapter:
        name = settings.adapters.secret_store
        if name not in _KNOWN_SECRET_STORE:
            raise ConfigurationError(
                f"Unknown secret_store adapter '{name}'. "
                f"Valid options: {sorted(_KNOWN_SECRET_STORE)}"
            )
        if name == "env":
            return EnvSecretStoreAdapter()
        return InMemorySecretStoreAdapter()

    @staticmethod
    def _build_metrics(settings: Settings) -> MetricsAdapter:
        name = settings.adapters.metrics
        if name not in _KNOWN_METRICS:
            raise ConfigurationError(
                f"Unknown metrics adapter '{name}'. "
                f"Valid options: {sorted(_KNOWN_METRICS)}"
            )
        if name == "in_memory":
            return InMemoryMetricsAdapter()
        return NoopMetricsAdapter()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def event_bus(self) -> EventBusAdapter:
        return self._event_bus

    @property
    def object_store(self) -> ObjectStoreAdapter:
        return self._object_store

    @property
    def secret_store(self) -> SecretStoreAdapter:
        return self._secret_store

    @property
    def metrics(self) -> MetricsAdapter:
        return self._metrics

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        await self._event_bus.close()
        await self._object_store.close()
        await self._secret_store.close()
        self._metrics.close()
