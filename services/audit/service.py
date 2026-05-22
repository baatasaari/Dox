"""Audit trail service — append-only governance action log."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import NotFoundError
from common.models.audit_log import AuditEntry
from common.schemas.audit_log import AuditEntryCreate


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, create: AuditEntryCreate) -> AuditEntry:
        entry = AuditEntry(
            tenant_id=create.tenant_id,
            actor_id=create.actor_id,
            actor_email=create.actor_email,
            action=create.action,
            resource_type=create.resource_type,
            resource_id=create.resource_id,
            summary=create.summary,
            extra=create.extra,
        )
        self._session.add(entry)
        await self._session.commit()
        return entry

    async def get(self, entry_id: UUID) -> AuditEntry:
        result = await self._session.execute(
            select(AuditEntry).where(AuditEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            raise NotFoundError(f"Audit entry {entry_id} not found")
        return entry

    async def list_for_tenant(
        self,
        tenant_id: str,
        *,
        action: str | None = None,
        resource_type: str | None = None,
        actor_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditEntry]:
        stmt = select(AuditEntry).where(AuditEntry.tenant_id == tenant_id)
        if action is not None:
            stmt = stmt.where(AuditEntry.action == action)
        if resource_type is not None:
            stmt = stmt.where(AuditEntry.resource_type == resource_type)
        if actor_id is not None:
            stmt = stmt.where(AuditEntry.actor_id == actor_id)
        stmt = stmt.order_by(AuditEntry.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_tenant(
        self,
        tenant_id: str,
        *,
        action: str | None = None,
        resource_type: str | None = None,
        actor_id: UUID | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(AuditEntry).where(
            AuditEntry.tenant_id == tenant_id
        )
        if action is not None:
            stmt = stmt.where(AuditEntry.action == action)
        if resource_type is not None:
            stmt = stmt.where(AuditEntry.resource_type == resource_type)
        if actor_id is not None:
            stmt = stmt.where(AuditEntry.actor_id == actor_id)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
