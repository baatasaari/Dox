"""Event bus adapter implementations."""
from __future__ import annotations

import copy
import json
from collections import defaultdict
from typing import Any

import redis.asyncio as aioredis

from .base import EventBusAdapter


class InMemoryEventBusAdapter(EventBusAdapter):
    """In-process event bus backed by a plain dict. For testing and local dev."""

    def __init__(self) -> None:
        self._store: dict[str, list[dict[str, Any]]] = defaultdict(list)

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        self._store[topic].append(copy.deepcopy(event))

    def get_events(self, topic: str) -> list[dict[str, Any]]:
        return list(self._store[topic])

    def clear(self) -> None:
        self._store.clear()

    async def close(self) -> None:
        pass


class RedisStreamsEventBusAdapter(EventBusAdapter):
    """Redis Streams-backed event bus. Events stored as JSON under the 'data' field."""

    def __init__(self, url: str, max_len: int = 10_000) -> None:
        self._url = url
        self._max_len = max_len
        self._client: aioredis.Redis | None = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(  # type: ignore[no-untyped-call]
                self._url, decode_responses=True
            )
        return self._client

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        client = await self._get_client()
        await client.xadd(topic, {"data": json.dumps(event)}, maxlen=self._max_len)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
