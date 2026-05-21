"""Module 2 — Adapters: Object store tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from common.adapters.object_store import InMemoryObjectStoreAdapter, LocalFsObjectStoreAdapter

# ---------------------------------------------------------------------------
# InMemoryObjectStoreAdapter
# ---------------------------------------------------------------------------


@pytest.fixture()
def mem_store() -> InMemoryObjectStoreAdapter:
    return InMemoryObjectStoreAdapter()


class TestInMemoryObjectStoreAdapter:
    async def test_put_and_get_round_trip(self, mem_store: InMemoryObjectStoreAdapter) -> None:
        await mem_store.put("key1", b"hello world")
        assert await mem_store.get("key1") == b"hello world"

    async def test_get_missing_key_raises_key_error(
        self, mem_store: InMemoryObjectStoreAdapter
    ) -> None:
        with pytest.raises(KeyError):
            await mem_store.get("nonexistent")

    async def test_exists_true_after_put(self, mem_store: InMemoryObjectStoreAdapter) -> None:
        await mem_store.put("k", b"data")
        assert await mem_store.exists("k") is True

    async def test_exists_false_for_unknown_key(
        self, mem_store: InMemoryObjectStoreAdapter
    ) -> None:
        assert await mem_store.exists("missing") is False

    async def test_delete_removes_object(self, mem_store: InMemoryObjectStoreAdapter) -> None:
        await mem_store.put("k", b"data")
        await mem_store.delete("k")
        assert await mem_store.exists("k") is False

    async def test_delete_nonexistent_key_is_safe(
        self, mem_store: InMemoryObjectStoreAdapter
    ) -> None:
        await mem_store.delete("ghost")

    async def test_overwrite_replaces_data(self, mem_store: InMemoryObjectStoreAdapter) -> None:
        await mem_store.put("k", b"v1")
        await mem_store.put("k", b"v2")
        assert await mem_store.get("k") == b"v2"

    async def test_empty_bytes_accepted(self, mem_store: InMemoryObjectStoreAdapter) -> None:
        await mem_store.put("empty", b"")
        assert await mem_store.get("empty") == b""

    async def test_close_is_safe(self, mem_store: InMemoryObjectStoreAdapter) -> None:
        await mem_store.close()


# ---------------------------------------------------------------------------
# LocalFsObjectStoreAdapter
# ---------------------------------------------------------------------------


@pytest.fixture()
def fs_store(tmp_path: Path) -> LocalFsObjectStoreAdapter:
    return LocalFsObjectStoreAdapter(base_path=str(tmp_path))


class TestLocalFsObjectStoreAdapter:
    async def test_put_and_get_round_trip(self, fs_store: LocalFsObjectStoreAdapter) -> None:
        await fs_store.put("file.bin", b"binary data")
        assert await fs_store.get("file.bin") == b"binary data"

    async def test_get_missing_raises_key_error(
        self, fs_store: LocalFsObjectStoreAdapter
    ) -> None:
        with pytest.raises(KeyError):
            await fs_store.get("ghost.bin")

    async def test_exists_true_after_put(self, fs_store: LocalFsObjectStoreAdapter) -> None:
        await fs_store.put("x", b"1")
        assert await fs_store.exists("x") is True

    async def test_exists_false_for_missing(self, fs_store: LocalFsObjectStoreAdapter) -> None:
        assert await fs_store.exists("nope") is False

    async def test_delete_removes_file(self, fs_store: LocalFsObjectStoreAdapter) -> None:
        await fs_store.put("f", b"data")
        await fs_store.delete("f")
        assert await fs_store.exists("f") is False

    async def test_delete_nonexistent_is_safe(
        self, fs_store: LocalFsObjectStoreAdapter
    ) -> None:
        await fs_store.delete("ghost")

    async def test_nested_key_creates_subdirectory(
        self, fs_store: LocalFsObjectStoreAdapter
    ) -> None:
        await fs_store.put("a/b/c.txt", b"nested")
        assert await fs_store.get("a/b/c.txt") == b"nested"

    async def test_overwrite_replaces_file(self, fs_store: LocalFsObjectStoreAdapter) -> None:
        await fs_store.put("k", b"old")
        await fs_store.put("k", b"new")
        assert await fs_store.get("k") == b"new"

    async def test_path_traversal_raises(self, fs_store: LocalFsObjectStoreAdapter) -> None:
        with pytest.raises(ValueError, match="escapes the storage root"):
            await fs_store.put("../evil.txt", b"bad")

    async def test_path_traversal_via_nested_raises(
        self, fs_store: LocalFsObjectStoreAdapter
    ) -> None:
        with pytest.raises(ValueError, match="escapes the storage root"):
            await fs_store.get("sub/../../etc/passwd")

    async def test_close_is_safe(self, fs_store: LocalFsObjectStoreAdapter) -> None:
        await fs_store.close()
