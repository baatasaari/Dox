"""FastAPI dependency for PolicyEvaluatorService."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_session

from .service import PolicyEvaluatorService


async def get_policy_evaluator(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PolicyEvaluatorService:
    return PolicyEvaluatorService(session)
