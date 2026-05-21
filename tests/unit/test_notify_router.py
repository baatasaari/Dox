"""Module 8 — Notify: HTTP route tests."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from common.exceptions import NotFoundError
from common.models.webhook import WebhookEndpoint
from common.schemas.webhook import DispatchResult, WebhookDeliveryResult
from services.notify.deps import get_notify_service
from services.notify.router import router
from services.notify.service import NotificationService


def _make_webhook() -> WebhookEndpoint:
    return WebhookEndpoint(
        id=uuid4(),
        tenant_id="tenant-acme",
        url="https://example.com/hook",
        secret="supersecretkey1234",
        event_types=["*"],
    )


def _make_mock_service() -> MagicMock:
    svc = MagicMock(spec=NotificationService)
    w = _make_webhook()
    svc.register_webhook = AsyncMock(return_value=w)
    svc.list_webhooks = AsyncMock(return_value=[w])
    svc.get_webhook = AsyncMock(return_value=w)
    svc.deactivate_webhook = AsyncMock(return_value=w)
    svc.dispatch = AsyncMock(
        return_value=DispatchResult(
            deliveries=[
                WebhookDeliveryResult(
                    webhook_id=w.id,
                    url=w.url,
                    success=True,
                    status_code=200,
                    error=None,
                    delivered_at=datetime.now(UTC),
                )
            ],
            successful=1,
            failed=0,
        )
    )
    return svc


@pytest.fixture()
async def client() -> AsyncGenerator[tuple[AsyncClient, MagicMock], None]:
    app = FastAPI()
    app.include_router(router)
    mock_svc = _make_mock_service()

    async def override() -> NotificationService:
        return mock_svc  # type: ignore[return-value]

    app.dependency_overrides[get_notify_service] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_svc  # type: ignore[misc]


class TestRegisterWebhookEndpoint:
    async def test_returns_201(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/notify/webhooks",
            json={
                "tenant_id": "t",
                "url": "https://example.com/hook",
                "secret": "a" * 16,
            },
        )
        assert r.status_code == 201

    async def test_response_shape(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/notify/webhooks",
            json={"tenant_id": "t", "url": "https://example.com/hook", "secret": "a" * 16},
        )
        body = r.json()
        assert "id" in body
        assert "url" in body
        assert "event_types" in body
        assert "secret" not in body  # secret never returned

    async def test_invalid_url_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/notify/webhooks",
            json={"tenant_id": "t", "url": "ftp://bad.com/hook", "secret": "a" * 16},
        )
        assert r.status_code == 422

    async def test_short_secret_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/notify/webhooks",
            json={"tenant_id": "t", "url": "https://example.com", "secret": "short"},
        )
        assert r.status_code == 422


class TestListWebhooksEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get("/v1/notify/webhooks", params={"tenant_id": "tenant-acme"})
        assert r.status_code == 200

    async def test_response_has_webhooks_and_total(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get("/v1/notify/webhooks", params={"tenant_id": "tenant-acme"})
        body = r.json()
        assert "webhooks" in body
        assert "total" in body

    async def test_missing_tenant_id_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get("/v1/notify/webhooks")
        assert r.status_code == 422

    async def test_secret_not_in_list_response(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get("/v1/notify/webhooks", params={"tenant_id": "t"})
        for w in r.json()["webhooks"]:
            assert "secret" not in w


class TestGetWebhookEndpoint:
    async def test_returns_200_when_found(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get(f"/v1/notify/webhooks/{uuid4()}")
        assert r.status_code == 200

    async def test_returns_404_when_missing(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.get_webhook = AsyncMock(side_effect=NotFoundError("gone"))
        r = await ac.get(f"/v1/notify/webhooks/{uuid4()}")
        assert r.status_code == 404

    async def test_invalid_uuid_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get("/v1/notify/webhooks/not-a-uuid")
        assert r.status_code == 422


class TestDeactivateWebhookEndpoint:
    async def test_returns_204(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.delete(f"/v1/notify/webhooks/{uuid4()}")
        assert r.status_code == 204

    async def test_returns_404_when_missing(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.deactivate_webhook = AsyncMock(side_effect=NotFoundError("gone"))
        r = await ac.delete(f"/v1/notify/webhooks/{uuid4()}")
        assert r.status_code == 404


class TestDispatchEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/notify/dispatch",
            json={"tenant_id": "t", "sentinel_type": "drift", "payload": {}},
        )
        assert r.status_code == 200

    async def test_response_shape(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/notify/dispatch",
            json={"tenant_id": "t", "sentinel_type": "drift", "payload": {}},
        )
        body = r.json()
        assert "deliveries" in body
        assert "successful" in body
        assert "failed" in body

    async def test_missing_tenant_id_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/notify/dispatch",
            json={"sentinel_type": "drift", "payload": {}},
        )
        assert r.status_code == 422

    async def test_delivery_result_fields(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/notify/dispatch",
            json={"tenant_id": "t", "sentinel_type": "drift", "payload": {}},
        )
        deliveries = r.json()["deliveries"]
        assert len(deliveries) == 1
        d = deliveries[0]
        assert "webhook_id" in d
        assert "success" in d
        assert "delivered_at" in d
