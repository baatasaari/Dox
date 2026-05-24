"""FastAPI dependency providers for the compliance service."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_session

from .service import ComplianceService


async def get_compliance_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ComplianceService:
    return ComplianceService(session=session)
