"""FastAPI dependency providers for the audit trail service."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_session

from .service import AuditService


async def get_audit_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuditService:
    return AuditService(session=session)
