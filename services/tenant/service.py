"""Tenant management service — CRUD for Tenant records."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import ConflictError, NotFoundError
from common.models.tenant import Tenant
from common.schemas.tenant import TenantCreate, TenantUpdate


class TenantService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, create: TenantCreate) -> Tenant:
        existing = await self._get_by_slug(create.slug)
        if existing is not None:
            raise ConflictError(f"Tenant with slug '{create.slug}' already exists")
        tenant = Tenant(
            slug=create.slug,
            name=create.name,
            subscription_tier=str(create.subscription_tier),
        )
        self._session.add(tenant)
        await self._session.commit()
        return tenant

    async def get(self, tenant_id: UUID) -> Tenant:
        result = await self._session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        if tenant is None:
            raise NotFoundError(f"Tenant {tenant_id} not found")
        return tenant

    async def get_by_slug(self, slug: str) -> Tenant:
        tenant = await self._get_by_slug(slug)
        if tenant is None:
            raise NotFoundError(f"Tenant '{slug}' not found")
        return tenant

    async def list_tenants(
        self,
        *,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Tenant]:
        stmt = select(Tenant)
        if active_only:
            stmt = stmt.where(Tenant.is_active.is_(True))
        stmt = stmt.order_by(Tenant.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, tenant_id: UUID, update: TenantUpdate) -> Tenant:
        tenant = await self.get(tenant_id)
        patch = update.model_dump(exclude_none=True)
        for field, value in patch.items():
            setattr(tenant, field, value if not hasattr(value, "value") else str(value))
        await self._session.commit()
        return tenant

    async def deactivate(self, tenant_id: UUID) -> None:
        tenant = await self.get(tenant_id)
        tenant.is_active = False
        await self._session.commit()

    async def activate(self, tenant_id: UUID) -> Tenant:
        tenant = await self.get(tenant_id)
        tenant.is_active = True
        await self._session.commit()
        return tenant

    async def _get_by_slug(self, slug: str) -> Tenant | None:
        result = await self._session.execute(
            select(Tenant).where(Tenant.slug == slug)
        )
        return result.scalar_one_or_none()
