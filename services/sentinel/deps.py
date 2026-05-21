"""Sentinel service FastAPI dependencies."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_session

from .service import SentinelService


async def get_sentinel_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SentinelService:
    return SentinelService(session)
