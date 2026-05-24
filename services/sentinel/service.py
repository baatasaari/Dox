"""Sentinel service — alert management and policy-based event evaluation."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import NotFoundError
from common.models.policy import Policy
from common.models.sentinel import SentinelAlert
from common.schemas.enums import EventType, InterventionAction, SentinelType, Severity
from common.schemas.events import CanonicalEvent
from common.schemas.sentinel import PolicyCreate, SentinelAlertCreate

# Maps event types that automatically trigger sentinel alerts.
_TRIGGER_MAP: dict[str, tuple[SentinelType, Severity]] = {
    EventType.tool_call_blocked: (SentinelType.tool_misuse, Severity.high),
    EventType.tool_call_failed: (SentinelType.tool_misuse, Severity.medium),
    EventType.policy_failed: (SentinelType.policy_breach, Severity.high),
    EventType.memory_write_blocked: (SentinelType.memory, Severity.high),
    EventType.memory_rollback: (SentinelType.memory, Severity.medium),
    EventType.agent_failed: (SentinelType.trajectory, Severity.high),
    EventType.agent_terminated: (SentinelType.trajectory, Severity.critical),
}


class SentinelService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------

    async def create_alert(self, create: SentinelAlertCreate) -> SentinelAlert:
        alert = SentinelAlert(
            id=uuid4(),
            event_id=create.event_id,
            tenant_id=create.tenant_id,
            agent_id=create.agent_id,
            sentinel_type=create.sentinel_type,
            severity=create.severity,
            message=create.message,
            details=create.details,
        )
        self._session.add(alert)
        await self._session.commit()
        return alert

    async def get_alert(self, alert_id: UUID) -> SentinelAlert:
        result = await self._session.execute(
            select(SentinelAlert).where(SentinelAlert.id == alert_id)
        )
        alert = result.scalar_one_or_none()
        if alert is None:
            raise NotFoundError(f"Alert {alert_id} not found")
        return alert

    async def list_alerts(
        self,
        tenant_id: str,
        *,
        severity: Severity | None = None,
        sentinel_type: SentinelType | None = None,
        is_resolved: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SentinelAlert]:
        filters = [SentinelAlert.tenant_id == tenant_id]
        if severity is not None:
            filters.append(SentinelAlert.severity == severity)
        if sentinel_type is not None:
            filters.append(SentinelAlert.sentinel_type == sentinel_type)
        if is_resolved is not None:
            filters.append(SentinelAlert.is_resolved.is_(is_resolved))
        result = await self._session.execute(
            select(SentinelAlert)
            .where(and_(*filters))
            .order_by(SentinelAlert.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def resolve_alert(
        self, alert_id: UUID, action: InterventionAction
    ) -> SentinelAlert:
        alert = await self.get_alert(alert_id)
        alert.is_resolved = True
        alert.action_taken = action
        alert.resolved_at = datetime.now(UTC)
        await self._session.commit()
        return alert

    # ------------------------------------------------------------------
    # Policies
    # ------------------------------------------------------------------

    async def create_policy(self, create: PolicyCreate) -> Policy:
        policy = Policy(
            id=uuid4(),
            tenant_id=create.tenant_id,
            name=create.name,
            description=create.description,
            sentinel_type=create.sentinel_type,
            severity=create.severity,
            action=create.action,
            config=create.config,
        )
        self._session.add(policy)
        await self._session.commit()
        return policy

    async def list_policies(
        self, tenant_id: str, *, active_only: bool = True
    ) -> list[Policy]:
        filters = [Policy.tenant_id == tenant_id]
        if active_only:
            filters.append(Policy.is_active.is_(True))
        result = await self._session.execute(
            select(Policy).where(and_(*filters)).order_by(Policy.created_at.desc())
        )
        return list(result.scalars().all())

    async def deactivate_policy(self, policy_id: UUID) -> Policy:
        result = await self._session.execute(
            select(Policy).where(Policy.id == policy_id)
        )
        policy = result.scalar_one_or_none()
        if policy is None:
            raise NotFoundError(f"Policy {policy_id} not found")
        policy.is_active = False
        await self._session.commit()
        return policy

    # ------------------------------------------------------------------
    # Event evaluation (pure Python — no DB required)
    # ------------------------------------------------------------------

    @staticmethod
    def evaluate_event(event: CanonicalEvent) -> list[SentinelAlertCreate]:
        trigger = _TRIGGER_MAP.get(event.event_type)
        if trigger is None:
            return []
        sentinel_type, severity = trigger
        return [
            SentinelAlertCreate(
                event_id=event.event_id,
                tenant_id=event.tenant_id,
                agent_id=event.agent_id,
                sentinel_type=sentinel_type,
                severity=severity,
                message=(
                    f"{sentinel_type} detected: {event.event_type} "
                    f"from agent {event.agent_id}"
                ),
                details={"event_type": event.event_type, "payload": event.payload},
            )
        ]
