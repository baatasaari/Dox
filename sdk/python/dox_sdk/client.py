"""DoxClient — async HTTP client for emitting events to the Dox platform."""
from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from common.schemas.events import CanonicalEvent

from .result import BatchEmitResult, EmitResult

_log = logging.getLogger(__name__)


@runtime_checkable
class AsyncHttpClient(Protocol):
    async def post(
        self,
        url: str,
        *,
        json: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> Any: ...

    async def aclose(self) -> None: ...


class DoxClient:
    """Async client for submitting CanonicalEvents to the Dox ingestion API.

    Designed for fire-and-forget use: by default it logs errors without raising,
    so a Dox outage never interrupts the agent it's instrumenting.

    Usage::

        async with DoxClient("https://dox.example.com", token="…") as client:
            await client.emit(event)
    """

    def __init__(
        self,
        base_url: str,
        api_token: str,
        *,
        timeout: float = 5.0,
        raise_on_error: bool = False,
        http_client: AsyncHttpClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = api_token
        self._timeout = timeout
        self._raise_on_error = raise_on_error
        self._http = http_client
        self._owned_client = http_client is None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _ensure_client(self) -> AsyncHttpClient:
        if self._http is None:
            import httpx

            self._http = httpx.AsyncClient()
        return self._http

    async def close(self) -> None:
        if self._http is not None and self._owned_client:
            await self._http.aclose()
            self._http = None

    async def __aenter__(self) -> DoxClient:
        await self._ensure_client()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Emission
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def emit(self, event: CanonicalEvent) -> EmitResult:
        """Submit a single event; returns EmitResult (never raises by default)."""
        http = await self._ensure_client()
        url = f"{self._base_url}/v1/events"
        try:
            response = await http.post(
                url,
                json=event.model_dump(mode="json"),
                headers=self._headers(),
                timeout=self._timeout,
            )
            status = response.status_code
            success = status in (200, 202)
            if success:
                body = response.json()
                return EmitResult(
                    success=True,
                    event_id=UUID(body["event_id"]),
                    status_code=status,
                )
            error_msg = f"HTTP {status}"
            if self._raise_on_error:
                raise RuntimeError(error_msg)
            _log.warning("dox emit failed: %s", error_msg)
            return EmitResult(success=False, status_code=status, error=error_msg)
        except Exception as exc:
            if self._raise_on_error:
                raise
            _log.warning("dox emit error: %s", exc)
            return EmitResult(success=False, error=str(exc))

    async def emit_batch(self, events: list[CanonicalEvent]) -> BatchEmitResult:
        """Submit up to 100 events in a single request."""
        if not events:
            return BatchEmitResult(success=True, accepted=0)

        http = await self._ensure_client()
        url = f"{self._base_url}/v1/events/batch"
        payload = {"events": [e.model_dump(mode="json") for e in events]}
        try:
            response = await http.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=self._timeout,
            )
            status = response.status_code
            success = status in (200, 202)
            if success:
                body = response.json()
                return BatchEmitResult(
                    success=True,
                    accepted=body["accepted"],
                    event_ids=[UUID(eid) for eid in body["event_ids"]],
                    status_code=status,
                )
            error_msg = f"HTTP {status}"
            if self._raise_on_error:
                raise RuntimeError(error_msg)
            _log.warning("dox batch emit failed: %s", error_msg)
            return BatchEmitResult(success=False, status_code=status, error=error_msg)
        except Exception as exc:
            if self._raise_on_error:
                raise
            _log.warning("dox batch emit error: %s", exc)
            return BatchEmitResult(success=False, error=str(exc))
