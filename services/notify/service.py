"""Notification service — webhook registration and signed HTTP delivery."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import NotFoundError
from common.models.webhook import WebhookEndpoint
from common.schemas.webhook import (
    DispatchRequest,
    DispatchResult,
    WebhookCreate,
    WebhookDeliveryResult,
)


@runtime_checkable
class AsyncHttpClient(Protocol):
    async def post(
        self,
        url: str,
        *,
        content: bytes,
        headers: dict[str, str],
        timeout: float,
    ) -> Any: ...


class NotificationService:
    def __init__(
        self,
        session: AsyncSession,
        http_client: AsyncHttpClient | None = None,
    ) -> None:
        self._session = session
        self._http = http_client

    # ------------------------------------------------------------------
    # Webhook CRUD
    # ------------------------------------------------------------------

    async def register_webhook(self, create: WebhookCreate) -> WebhookEndpoint:
        webhook = WebhookEndpoint(
            id=uuid4(),
            tenant_id=create.tenant_id,
            url=create.url,
            secret=create.secret,
            event_types=create.event_types,
            description=create.description,
        )
        self._session.add(webhook)
        await self._session.commit()
        return webhook

    async def get_webhook(self, webhook_id: UUID) -> WebhookEndpoint:
        result = await self._session.execute(
            select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id)
        )
        webhook = result.scalar_one_or_none()
        if webhook is None:
            raise NotFoundError(f"Webhook {webhook_id} not found")
        return webhook

    async def list_webhooks(
        self, tenant_id: str, *, active_only: bool = True
    ) -> list[WebhookEndpoint]:
        conditions = [WebhookEndpoint.tenant_id == tenant_id]
        if active_only:
            conditions.append(WebhookEndpoint.is_active.is_(True))
        result = await self._session.execute(
            select(WebhookEndpoint)
            .where(and_(*conditions))
            .order_by(WebhookEndpoint.created_at.desc())
        )
        return list(result.scalars().all())

    async def deactivate_webhook(self, webhook_id: UUID) -> WebhookEndpoint:
        webhook = await self.get_webhook(webhook_id)
        webhook.is_active = False
        await self._session.commit()
        return webhook

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def dispatch(self, request: DispatchRequest) -> DispatchResult:
        webhooks = await self.list_webhooks(request.tenant_id, active_only=True)
        matching = [
            w
            for w in webhooks
            if "*" in w.event_types or request.sentinel_type in w.event_types
        ]

        deliveries: list[WebhookDeliveryResult] = []
        for webhook in matching:
            result = await self._deliver(webhook, request.sentinel_type, request.payload)
            deliveries.append(result)

        successful = sum(1 for d in deliveries if d.success)
        return DispatchResult(
            deliveries=deliveries,
            successful=successful,
            failed=len(deliveries) - successful,
        )

    async def _deliver(
        self,
        webhook: WebhookEndpoint,
        sentinel_type: str,
        payload: dict[str, Any],
    ) -> WebhookDeliveryResult:
        delivery_id = str(uuid4())
        now = datetime.now(UTC)
        body = json.dumps(
            {
                "delivery_id": delivery_id,
                "sentinel_type": sentinel_type,
                "payload": payload,
                "delivered_at": now.isoformat(),
            },
            sort_keys=True,
        ).encode("utf-8")

        signature = self.sign_payload(body, webhook.secret)
        headers = {
            "Content-Type": "application/json",
            "X-Dox-Signature-256": signature,
            "X-Dox-Delivery": delivery_id,
        }

        success = False
        status_code: int | None = None
        error: str | None = None

        if self._http is not None:
            try:
                response = await self._http.post(
                    webhook.url,
                    content=body,
                    headers=headers,
                    timeout=10.0,
                )
                status_code = response.status_code
                success = 200 <= status_code < 300
                if not success:
                    error = f"HTTP {status_code}"
            except Exception as exc:
                error = str(exc)

        webhook.last_delivered_at = now
        if success:
            webhook.failure_count = 0
        else:
            webhook.failure_count = (webhook.failure_count or 0) + 1
        await self._session.commit()

        return WebhookDeliveryResult(
            webhook_id=webhook.id,
            url=webhook.url,
            success=success,
            status_code=status_code,
            error=error,
            delivered_at=now,
        )

    # ------------------------------------------------------------------
    # Signing
    # ------------------------------------------------------------------

    @staticmethod
    def sign_payload(body: bytes, secret: str) -> str:
        """Return HMAC-SHA256 signature in the form ``sha256=<hex>``."""
        digest = hmac.new(
            key=secret.encode("utf-8"),
            msg=body,
            digestmod=hashlib.sha256,
        ).hexdigest()
        return f"sha256={digest}"
