"""Module C — Tenant isolation under real PostgreSQL constraints.

What this proves
----------------
1. ``UniqueConstraint("tenant_id", "agent_id")`` on ``agent_profiles``:
   - Same ``agent_id`` in *different* tenants: both rows insert successfully.
   - Same ``agent_id`` in the *same* tenant: Postgres raises IntegrityError.

2. Query-level isolation:
   - A SELECT filtered to tenant A returns zero rows owned by tenant B.
   - This holds at the raw ORM level and through the service layer.

3. Quota uniqueness:
   - ``tenant_quotas.tenant_id`` is UNIQUE; a second provision upserts, not
     duplicates.

Every test runs inside a real transaction that is rolled back unconditionally,
so no data persists between tests.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy.exc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.agent import AgentProfile
from common.models.quota import TenantQuota
from common.schemas.agent import AgentProfileCreate
from common.schemas.quota import QuotaProvision
from services.quota.service import QuotaService
from services.registry.service import AgentRegistryService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _agent(tenant_id: str, agent_id: str, name: str = "Bot") -> AgentProfile:
    return AgentProfile(tenant_id=tenant_id, agent_id=agent_id, name=name, version="1.0")


def _uid() -> str:
    return uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAgentProfileUniqueConstraint:
    """The DB-level UniqueConstraint("tenant_id", "agent_id") behaves correctly."""

    async def test_same_agent_id_in_different_tenants_both_succeed(
        self, db_session: AsyncSession
    ) -> None:
        """Cross-tenant rows with identical agent_ids must coexist."""
        agent_id = f"shared-agent-{_uid()}"

        db_session.add(_agent("tenant-alpha", agent_id))
        db_session.add(_agent("tenant-beta", agent_id))
        await db_session.flush()

        result = await db_session.execute(
            select(AgentProfile).where(AgentProfile.agent_id == agent_id)
        )
        rows = result.scalars().all()

        assert len(rows) == 2
        assert {r.tenant_id for r in rows} == {"tenant-alpha", "tenant-beta"}

    async def test_duplicate_agent_id_same_tenant_raises_integrity_error(
        self, db_session: AsyncSession
    ) -> None:
        """A second (tenant_id, agent_id) pair must fail at the Postgres level."""
        tenant = f"tenant-{_uid()}"
        agent_id = f"agent-{_uid()}"

        db_session.add(_agent(tenant, agent_id, name="First"))
        await db_session.flush()

        # Use an explicit savepoint so we can roll back the failed insert while
        # keeping the outer transaction (and the first row) intact.
        sp = await db_session.begin_nested()
        db_session.add(_agent(tenant, agent_id, name="Duplicate"))
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await db_session.flush()
        await sp.rollback()  # ROLLBACK TO SAVEPOINT — clears error state

        # First row still exists; duplicate did not survive.
        result = await db_session.execute(
            select(AgentProfile).where(
                AgentProfile.tenant_id == tenant,
                AgentProfile.agent_id == agent_id,
            )
        )
        survivors = result.scalars().all()
        assert len(survivors) == 1
        assert survivors[0].name == "First"

    async def test_many_tenants_same_agent_id_all_succeed(
        self, db_session: AsyncSession
    ) -> None:
        """The constraint is scoped to (tenant_id, agent_id) — N tenants, no collision."""
        agent_id = f"universal-agent-{_uid()}"
        tenants = [f"tenant-{_uid()}" for _ in range(5)]

        for t in tenants:
            db_session.add(_agent(t, agent_id))
        await db_session.flush()

        result = await db_session.execute(
            select(AgentProfile).where(AgentProfile.agent_id == agent_id)
        )
        assert len(result.scalars().all()) == 5


class TestQueryScopedByTenant:
    """SELECT queries filtered by tenant_id must never leak rows across tenants."""

    async def test_orm_query_returns_only_own_tenant_rows(
        self, db_session: AsyncSession
    ) -> None:
        tenant_a = f"tenant-a-{_uid()}"
        tenant_b = f"tenant-b-{_uid()}"

        for i in range(3):
            db_session.add(_agent(tenant_a, f"agent-a-{i}"))
            db_session.add(_agent(tenant_b, f"agent-b-{i}"))
        await db_session.flush()

        result = await db_session.execute(
            select(AgentProfile).where(AgentProfile.tenant_id == tenant_a)
        )
        rows = result.scalars().all()

        assert len(rows) == 3, "Expected exactly 3 rows for tenant A"
        assert all(r.tenant_id == tenant_a for r in rows), (
            "Tenant B rows leaked into Tenant A query"
        )

    async def test_service_layer_list_scopes_to_tenant(
        self, db_session: AsyncSession
    ) -> None:
        """AgentRegistryService.list_for_tenant() must scope its SELECT to the given tenant."""
        tenant_a = f"tenant-a-{_uid()}"
        tenant_b = f"tenant-b-{_uid()}"

        # Insert via the service layer (exercises the real INSERT path).
        svc = AgentRegistryService(db_session)
        for i in range(2):
            await svc.create(
                AgentProfileCreate(
                    tenant_id=tenant_a, agent_id=f"svc-agent-a-{i}", name=f"A{i}"
                )
            )
            await svc.create(
                AgentProfileCreate(
                    tenant_id=tenant_b, agent_id=f"svc-agent-b-{i}", name=f"B{i}"
                )
            )

        agents_a = await svc.list_for_tenant(tenant_a)
        agents_b = await svc.list_for_tenant(tenant_b)

        assert len(agents_a) == 2
        assert len(agents_b) == 2
        assert all(a.tenant_id == tenant_a for a in agents_a)
        assert all(a.tenant_id == tenant_b for a in agents_b)

        # Cross-check: no agent from B appears in A's result set.
        a_ids = {a.agent_id for a in agents_a}
        b_ids = {a.agent_id for a in agents_b}
        assert a_ids.isdisjoint(b_ids), "agent_ids overlap between tenant A and B result sets"

    async def test_zero_rows_returned_for_unknown_tenant(
        self, db_session: AsyncSession
    ) -> None:
        """Querying a tenant that owns no rows returns an empty list, not an error."""
        result = await db_session.execute(
            select(AgentProfile).where(AgentProfile.tenant_id == f"ghost-tenant-{_uid()}")
        )
        assert result.scalars().all() == []


class TestQuotaUniquenessPerTenant:
    """tenant_quotas.tenant_id is UNIQUE — a second provision must upsert, not duplicate."""

    async def test_provision_twice_same_tenant_upserts_not_duplicates(
        self, db_session: AsyncSession
    ) -> None:
        tenant = f"tenant-{_uid()}"
        svc = QuotaService(db_session)

        await svc.provision(QuotaProvision(tenant_id=tenant, subscription_tier="starter"))
        await svc.provision(
            QuotaProvision(tenant_id=tenant, subscription_tier="professional")
        )

        result = await db_session.execute(
            select(TenantQuota).where(TenantQuota.tenant_id == tenant)
        )
        rows = result.scalars().all()

        assert len(rows) == 1, "Second provision must upsert, not insert a second row"
        assert rows[0].subscription_tier == "professional"

    async def test_quota_row_isolated_per_tenant(
        self, db_session: AsyncSession
    ) -> None:
        """Each tenant gets exactly one quota row; querying tenant A returns only A."""
        tenant_a = f"tenant-a-{_uid()}"
        tenant_b = f"tenant-b-{_uid()}"
        svc = QuotaService(db_session)

        await svc.provision(QuotaProvision(tenant_id=tenant_a, subscription_tier="starter"))
        await svc.provision(QuotaProvision(tenant_id=tenant_b, subscription_tier="professional"))

        result = await db_session.execute(
            select(TenantQuota).where(TenantQuota.tenant_id == tenant_a)
        )
        rows = result.scalars().all()

        assert len(rows) == 1
        assert rows[0].tenant_id == tenant_a
        assert rows[0].subscription_tier == "starter"
