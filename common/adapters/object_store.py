"""Object store adapter implementations."""
from __future__ import annotations

from pathlib import Path

from .base import ObjectStoreAdapter


class InMemoryObjectStoreAdapter(ObjectStoreAdapter):
    """In-process object store backed by a plain dict. For testing and local dev."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def put(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        self._store[key] = data

    async def get(self, key: str) -> bytes:
        if key not in self._store:
            raise KeyError(f"Object not found: {key!r}")
        return self._store[key]

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._store

    async def close(self) -> None:
        pass


class LocalFsObjectStoreAdapter(ObjectStoreAdapter):
    """Local-filesystem object store. Suitable for development; not for production."""

    def __init__(self, base_path: str = "local_fs_store") -> None:
        self._base = Path(base_path).resolve()
        self._base.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, key: str) -> Path:
        resolved = (self._base / key).resolve()
        try:
            resolved.relative_to(self._base)
        except ValueError:
            raise ValueError(f"Key {key!r} escapes the storage root") from None
        return resolved

    async def put(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        path = self._resolve_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get(self, key: str) -> bytes:
        path = self._resolve_path(key)
        if not path.exists():
            raise KeyError(f"Object not found: {key!r}")
        return path.read_bytes()

    async def delete(self, key: str) -> None:
        path = self._resolve_path(key)
        if path.exists():
            path.unlink()

    async def exists(self, key: str) -> bool:
        return self._resolve_path(key).exists()

    async def close(self) -> None:
        pass
