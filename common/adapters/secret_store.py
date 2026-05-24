"""Secret store adapter implementations."""
from __future__ import annotations

import os

from .base import SecretStoreAdapter


class EnvSecretStoreAdapter(SecretStoreAdapter):
    """Reads secrets from environment variables. Suitable for local dev and CI."""

    async def get_secret(self, name: str) -> str:
        value = os.environ.get(name)
        if value is None:
            raise KeyError(f"Secret not found in environment: {name!r}")
        return value

    async def close(self) -> None:
        pass


class InMemorySecretStoreAdapter(SecretStoreAdapter):
    """In-process secret store backed by a plain dict. For testing only."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def set_secret(self, name: str, value: str) -> None:
        self._store[name] = value

    def delete_secret(self, name: str) -> None:
        self._store.pop(name, None)

    async def get_secret(self, name: str) -> str:
        if name not in self._store:
            raise KeyError(f"Secret not found: {name!r}")
        return self._store[name]

    async def close(self) -> None:
        pass
