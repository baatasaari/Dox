"""Auth service — credential verification and token issuance."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.auth.passwords import verify_password
from common.auth.tokens import create_access_token
from common.config import settings
from common.models.user import User
from common.schemas.auth import TokenResponse


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def authenticate(self, email: str, password: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.email == email, User.is_active.is_(True))
        )
        user = result.scalar_one_or_none()
        if user is None or not verify_password(password, user.hashed_password):
            return None
        return user

    def create_token(self, user: User) -> TokenResponse:
        token = create_access_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            role=user.role,
        )
        return TokenResponse(
            access_token=token,
            expires_in=settings.auth.access_token_expire_minutes * 60,
        )
