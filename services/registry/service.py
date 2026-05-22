"""Agent Registry service — CRUD + heartbeat for AgentProfile records."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import ConflictError, NotFoundError
from common.models.agent import AgentProfile
from common.schemas.agent import AgentProfileCreate, AgentProfileUpdate


class AgentRegistryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, create: AgentProfileCreate) -> AgentProfile:
        existing = await self._get_by_tenant_and_agent(create.tenant_id, create.agent_id)
        if existing is not None:
            raise ConflictError(
                f"Agent '{create.agent_id}' already registered for tenant '{create.tenant_id}'"
            )
        profile = AgentProfile(
            tenant_id=create.tenant_id,
            agent_id=create.agent_id,
            name=create.name,
            description=create.description,
            version=create.version,
            capabilities=list(create.capabilities),
            tags=dict(create.tags),
        )
        self._session.add(profile)
        await self._session.commit()
        return profile

    async def get(self, profile_id: UUID) -> AgentProfile:
        result = await self._session.execute(
            select(AgentProfile).where(AgentProfile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            raise NotFoundError(f"AgentProfile {profile_id} not found")
        return profile

    async def get_by_agent_id(self, tenant_id: str, agent_id: str) -> AgentProfile:
        profile = await self._get_by_tenant_and_agent(tenant_id, agent_id)
        if profile is None:
            raise NotFoundError(f"Agent '{agent_id}' not found for tenant '{tenant_id}'")
        return profile

    async def list_for_tenant(
        self,
        tenant_id: str,
        *,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentProfile]:
        stmt = select(AgentProfile).where(AgentProfile.tenant_id == tenant_id)
        if active_only:
            stmt = stmt.where(AgentProfile.is_active.is_(True))
        stmt = stmt.order_by(AgentProfile.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, profile_id: UUID, update: AgentProfileUpdate) -> AgentProfile:
        profile = await self.get(profile_id)
        patch = update.model_dump(exclude_none=True)
        for field, value in patch.items():
            setattr(profile, field, value)
        await self._session.commit()
        return profile

    async def delete(self, profile_id: UUID) -> None:
        profile = await self.get(profile_id)
        profile.is_active = False
        await self._session.commit()

    async def heartbeat(self, tenant_id: str, agent_id: str) -> AgentProfile:
        profile = await self.get_by_agent_id(tenant_id, agent_id)
        profile.last_seen_at = datetime.now(UTC)
        await self._session.commit()
        return profile

    async def _get_by_tenant_and_agent(
        self, tenant_id: str, agent_id: str
    ) -> AgentProfile | None:
        result = await self._session.execute(
            select(AgentProfile).where(
                and_(
                    AgentProfile.tenant_id == tenant_id,
                    AgentProfile.agent_id == agent_id,
                )
            )
        )
        return result.scalar_one_or_none()
