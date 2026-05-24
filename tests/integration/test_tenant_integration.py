"""Integration: TenantService business logic with real model instances."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common.exceptions import ConflictError, NotFoundError
from common.models.tenant import Tenant
from common.schemas.enums import SubscriptionTier
from common.schemas.tenant import TenantCreate, TenantUpdate
from services.tenant.service import TenantService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tenant(
    slug: str = "acme",
    name: str = "Acme Corp",
    subscription_tier: str = "starter",
    is_active: bool = True,
) -> Tenant:
    return Tenant(
        id=uuid4(),
        slug=slug,
        name=name,
        subscription_tier=subscription_tier,
        is_active=is_active,
    )


def _session_for_get(tenant: Tenant | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = tenant
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _session_for_create(existing: Tenant | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _session_with_list(tenants: list[Tenant]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = tenants
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


class TestTenantCreation:
    async def test_create_new_tenant_with_defaults(self) -> None:
        session = _session_for_create(None)
        svc = TenantService(session)  # type: ignore[arg-type]

        tenant = await svc.create(TenantCreate(slug="new-co", name="New Co"))

        assert tenant.slug == "new-co"
        assert tenant.name == "New Co"
        assert tenant.subscription_tier == "starter"
        assert tenant.is_active is True
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    async def test_create_with_professional_tier(self) -> None:
        session = _session_for_create(None)
        svc = TenantService(session)  # type: ignore[arg-type]

        tenant = await svc.create(
            TenantCreate(
                slug="pro-co",
                name="Pro Co",
                subscription_tier=SubscriptionTier.professional,
            )
        )
        assert tenant.subscription_tier == "professional"

    async def test_duplicate_slug_raises_conflict(self) -> None:
        existing = _make_tenant(slug="taken")
        session = _session_for_create(existing)
        svc = TenantService(session)  # type: ignore[arg-type]

        with pytest.raises(ConflictError):
            await svc.create(TenantCreate(slug="taken", name="Dup"))

    async def test_different_slugs_do_not_conflict(self) -> None:
        session = _session_for_create(None)
        svc = TenantService(session)  # type: ignore[arg-type]

        tenant = await svc.create(TenantCreate(slug="unique-slug", name="Unique"))
        assert tenant.slug == "unique-slug"


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


class TestTenantLookup:
    async def test_get_by_id_returns_correct_tenant(self) -> None:
        t = _make_tenant()
        session = _session_for_get(t)
        svc = TenantService(session)  # type: ignore[arg-type]

        result = await svc.get(t.id)
        assert result.id == t.id

    async def test_get_missing_id_raises_not_found(self) -> None:
        session = _session_for_get(None)
        svc = TenantService(session)  # type: ignore[arg-type]

        with pytest.raises(NotFoundError):
            await svc.get(uuid4())

    async def test_get_by_slug_returns_tenant(self) -> None:
        t = _make_tenant(slug="find-me")
        session = _session_for_get(t)
        svc = TenantService(session)  # type: ignore[arg-type]

        result = await svc.get_by_slug("find-me")
        assert result.slug == "find-me"

    async def test_get_by_slug_missing_raises_not_found(self) -> None:
        session = _session_for_get(None)
        svc = TenantService(session)  # type: ignore[arg-type]

        with pytest.raises(NotFoundError):
            await svc.get_by_slug("ghost")


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


class TestTenantListing:
    async def test_list_returns_all_tenants(self) -> None:
        tenants = [_make_tenant(slug=f"org-{i}") for i in range(6)]
        session = _session_with_list(tenants)
        svc = TenantService(session)  # type: ignore[arg-type]

        result = await svc.list_tenants()
        assert len(result) == 6

    async def test_list_empty_returns_empty(self) -> None:
        session = _session_with_list([])
        svc = TenantService(session)  # type: ignore[arg-type]

        result = await svc.list_tenants()
        assert result == []


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class TestTenantUpdate:
    async def test_update_name(self) -> None:
        t = _make_tenant(name="before")
        session = _session_for_get(t)
        svc = TenantService(session)  # type: ignore[arg-type]

        result = await svc.update(t.id, TenantUpdate(name="after"))
        assert result.name == "after"

    async def test_update_subscription_tier(self) -> None:
        t = _make_tenant(subscription_tier="starter")
        session = _session_for_get(t)
        svc = TenantService(session)  # type: ignore[arg-type]

        result = await svc.update(
            t.id, TenantUpdate(subscription_tier=SubscriptionTier.enterprise)
        )
        assert result.subscription_tier == "enterprise"

    async def test_empty_update_leaves_fields_unchanged(self) -> None:
        t = _make_tenant(name="unchanged", subscription_tier="starter")
        session = _session_for_get(t)
        svc = TenantService(session)  # type: ignore[arg-type]

        result = await svc.update(t.id, TenantUpdate())
        assert result.name == "unchanged"
        assert result.subscription_tier == "starter"

    async def test_update_missing_raises_not_found(self) -> None:
        session = _session_for_get(None)
        svc = TenantService(session)  # type: ignore[arg-type]

        with pytest.raises(NotFoundError):
            await svc.update(uuid4(), TenantUpdate(name="x"))


# ---------------------------------------------------------------------------
# Deactivate / Activate lifecycle
# ---------------------------------------------------------------------------


class TestTenantLifecycle:
    async def test_deactivate_sets_inactive(self) -> None:
        t = _make_tenant(is_active=True)
        session = _session_for_get(t)
        svc = TenantService(session)  # type: ignore[arg-type]

        await svc.deactivate(t.id)
        assert t.is_active is False
        session.commit.assert_awaited_once()

    async def test_activate_sets_active(self) -> None:
        t = _make_tenant(is_active=False)
        session = _session_for_get(t)
        svc = TenantService(session)  # type: ignore[arg-type]

        result = await svc.activate(t.id)
        assert result.is_active is True
        session.commit.assert_awaited_once()

    async def test_deactivate_then_activate_roundtrip(self) -> None:
        t = _make_tenant(is_active=True)
        results = [MagicMock(), MagicMock()]
        results[0].scalar_one_or_none.return_value = t
        results[1].scalar_one_or_none.return_value = t
        session = MagicMock()
        session.execute = AsyncMock(side_effect=results)
        session.add = MagicMock()
        session.commit = AsyncMock()
        svc = TenantService(session)  # type: ignore[arg-type]

        await svc.deactivate(t.id)
        assert t.is_active is False

        await svc.activate(t.id)
        assert t.is_active is True

    async def test_deactivate_missing_raises_not_found(self) -> None:
        session = _session_for_get(None)
        svc = TenantService(session)  # type: ignore[arg-type]

        with pytest.raises(NotFoundError):
            await svc.deactivate(uuid4())

    async def test_activate_missing_raises_not_found(self) -> None:
        session = _session_for_get(None)
        svc = TenantService(session)  # type: ignore[arg-type]

        with pytest.raises(NotFoundError):
            await svc.activate(uuid4())
