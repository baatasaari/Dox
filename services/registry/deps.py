"""FastAPI dependency providers for the agent registry service."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_session

from .service import AgentRegistryService


async def get_registry_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentRegistryService:
    return AgentRegistryService(session=session)
