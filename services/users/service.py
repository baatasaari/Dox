"""User management service — CRUD + password management for User records."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.auth.passwords import hash_password
from common.exceptions import ConflictError, NotFoundError
from common.models.user import User
from common.schemas.user import UserCreate, UserUpdate


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, create: UserCreate) -> User:
        existing = await self._get_by_email(create.email)
        if existing is not None:
            raise ConflictError(f"User with email '{create.email}' already exists")
        user = User(
            email=create.email,
            hashed_password=hash_password(create.password),
            tenant_id=create.tenant_id,
            role=str(create.role),
        )
        self._session.add(user)
        await self._session.commit()
        return user

    async def get(self, user_id: UUID) -> User:
        result = await self._session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        return user

    async def get_by_email(self, email: str) -> User:
        user = await self._get_by_email(email)
        if user is None:
            raise NotFoundError(f"User '{email}' not found")
        return user

    async def list_for_tenant(
        self,
        tenant_id: str,
        *,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]:
        stmt = select(User).where(User.tenant_id == tenant_id)
        if active_only:
            stmt = stmt.where(User.is_active.is_(True))
        stmt = stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, user_id: UUID, update: UserUpdate) -> User:
        user = await self.get(user_id)
        patch = update.model_dump(exclude_none=True)
        for field, value in patch.items():
            setattr(user, field, str(value) if hasattr(value, "value") else value)
        await self._session.commit()
        return user

    async def deactivate(self, user_id: UUID) -> None:
        user = await self.get(user_id)
        user.is_active = False
        await self._session.commit()

    async def change_password(self, user_id: UUID, new_password: str) -> User:
        user = await self.get(user_id)
        user.hashed_password = hash_password(new_password)
        await self._session.commit()
        return user

    async def _get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
