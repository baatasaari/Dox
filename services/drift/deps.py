"""FastAPI dependency providers for the drift service."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_session

from .service import DriftDetectionService


async def get_drift_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DriftDetectionService:
    return DriftDetectionService(session=session)
