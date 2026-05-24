"""Module 2 — Adapters: Secret store tests."""
from __future__ import annotations

import pytest

from common.adapters.secret_store import EnvSecretStoreAdapter, InMemorySecretStoreAdapter


class TestEnvSecretStoreAdapter:
    async def test_get_secret_returns_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOX_TEST_SECRET_XYZ", "supersecret")
        adapter = EnvSecretStoreAdapter()
        assert await adapter.get_secret("DOX_TEST_SECRET_XYZ") == "supersecret"

    async def test_get_missing_secret_raises_key_error(self) -> None:
        adapter = EnvSecretStoreAdapter()
        with pytest.raises(KeyError):
            await adapter.get_secret("DEFINITELY_NOT_SET_XYZ_RANDOM_12345")

    async def test_empty_string_env_var_is_returned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DOX_EMPTY_SECRET", "")
        adapter = EnvSecretStoreAdapter()
        assert await adapter.get_secret("DOX_EMPTY_SECRET") == ""

    async def test_close_is_safe(self) -> None:
        adapter = EnvSecretStoreAdapter()
        await adapter.close()
        await adapter.close()


class TestInMemorySecretStoreAdapter:
    @pytest.fixture()
    def adapter(self) -> InMemorySecretStoreAdapter:
        return InMemorySecretStoreAdapter()

    async def test_set_and_get_secret(self, adapter: InMemorySecretStoreAdapter) -> None:
        adapter.set_secret("api_key", "abc123")
        assert await adapter.get_secret("api_key") == "abc123"

    async def test_get_missing_raises_key_error(
        self, adapter: InMemorySecretStoreAdapter
    ) -> None:
        with pytest.raises(KeyError):
            await adapter.get_secret("not_set")

    async def test_delete_removes_secret(self, adapter: InMemorySecretStoreAdapter) -> None:
        adapter.set_secret("k", "v")
        adapter.delete_secret("k")
        with pytest.raises(KeyError):
            await adapter.get_secret("k")

    async def test_delete_nonexistent_is_safe(
        self, adapter: InMemorySecretStoreAdapter
    ) -> None:
        adapter.delete_secret("ghost")

    async def test_overwrite_replaces_value(self, adapter: InMemorySecretStoreAdapter) -> None:
        adapter.set_secret("k", "v1")
        adapter.set_secret("k", "v2")
        assert await adapter.get_secret("k") == "v2"

    async def test_multiple_secrets_are_independent(
        self, adapter: InMemorySecretStoreAdapter
    ) -> None:
        adapter.set_secret("a", "alpha")
        adapter.set_secret("b", "beta")
        assert await adapter.get_secret("a") == "alpha"
        assert await adapter.get_secret("b") == "beta"

    async def test_close_is_safe(self, adapter: InMemorySecretStoreAdapter) -> None:
        await adapter.close()
        await adapter.close()
