"""FastAPI dependency providers for the playback service."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_session

from .service import PlaybackService


async def get_playback_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PlaybackService:
    return PlaybackService(session=session)
