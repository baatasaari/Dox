"""FastAPI dependency providers for the quota service."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_session

from .service import QuotaService


async def get_quota_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> QuotaService:
    return QuotaService(session=session)
