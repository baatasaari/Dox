"""FastAPI dependency providers for the query service."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_session

from .service import EventQueryService


async def get_query_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventQueryService:
    return EventQueryService(session=session)
