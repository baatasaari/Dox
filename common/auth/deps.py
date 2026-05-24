"""FastAPI auth dependencies — current user resolution and role enforcement."""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.auth.tokens import decode_access_token
from common.db import get_session
from common.exceptions import AuthenticationError
from common.models.user import User

_bearer = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    try:
        payload = decode_access_token(credentials.credentials)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    result = await session.execute(
        select(User).where(User.id == UUID(payload.sub), User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(*roles: str) -> Any:
    """Dependency factory — raises 403 if the current user's role is not in *roles*."""

    async def _check(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return Depends(_check)
