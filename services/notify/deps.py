"""FastAPI dependency providers for the notification service."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_session

from .service import NotificationService


async def get_notify_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NotificationService:
    return NotificationService(session=session)
