"""Notification service HTTP routes — webhook management and delivery."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from common.exceptions import NotFoundError
from common.schemas.webhook import (
    DispatchRequest,
    DispatchResult,
    WebhookCreate,
    WebhookListResponse,
    WebhookResponse,
)

from .deps import get_notify_service
from .service import NotificationService

router = APIRouter(prefix="/v1/notify", tags=["notify"])


@router.post(
    "/webhooks",
    status_code=status.HTTP_201_CREATED,
    response_model=WebhookResponse,
)
async def register_webhook(
    create: WebhookCreate,
    service: Annotated[NotificationService, Depends(get_notify_service)],
) -> WebhookResponse:
    webhook = await service.register_webhook(create)
    return WebhookResponse.model_validate(webhook)


@router.get("/webhooks", response_model=WebhookListResponse)
async def list_webhooks(
    tenant_id: str,
    service: Annotated[NotificationService, Depends(get_notify_service)],
    active_only: Annotated[bool, Query()] = True,
) -> WebhookListResponse:
    webhooks = await service.list_webhooks(tenant_id, active_only=active_only)
    return WebhookListResponse(
        webhooks=[WebhookResponse.model_validate(w) for w in webhooks],
        total=len(webhooks),
    )


@router.get("/webhooks/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
    webhook_id: UUID,
    service: Annotated[NotificationService, Depends(get_notify_service)],
) -> WebhookResponse:
    try:
        webhook = await service.get_webhook(webhook_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found"
        )
    return WebhookResponse.model_validate(webhook)


@router.delete(
    "/webhooks/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def deactivate_webhook(
    webhook_id: UUID,
    service: Annotated[NotificationService, Depends(get_notify_service)],
) -> None:
    try:
        await service.deactivate_webhook(webhook_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found"
        )


@router.post("/dispatch", response_model=DispatchResult)
async def dispatch(
    request: DispatchRequest,
    service: Annotated[NotificationService, Depends(get_notify_service)],
) -> DispatchResult:
    return await service.dispatch(request)
