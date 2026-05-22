"""Module 12 — Tenant Management: service layer tests."""
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
    *,
    slug: str = "acme",
    name: str = "Acme Corp",
    subscription_tier: str = "starter",
    is_active: bool = True,
) -> Tenant:
    return Tenant(id=uuid4(), slug=slug, name=name, subscription_tier=subscription_tier,
                  is_active=is_active)


def _scalar_result(obj: object) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


def _scalars_result(items: list[object]) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _make_session(*results: MagicMock) -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=list(results))
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class TestCreateTenant:
    async def test_creates_tenant_when_slug_available(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = TenantService(session)  # type: ignore[arg-type]

        tenant = await svc.create(TenantCreate(slug="new-org", name="New Org"))

        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        assert tenant.slug == "new-org"
        assert tenant.name == "New Org"

    async def test_raises_conflict_on_duplicate_slug(self) -> None:
        existing = _make_tenant(slug="acme")
        session = _make_session(_scalar_result(existing))
        svc = TenantService(session)  # type: ignore[arg-type]

        with pytest.raises(ConflictError):
            await svc.create(TenantCreate(slug="acme", name="Acme 2"))

    async def test_subscription_tier_stored(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = TenantService(session)  # type: ignore[arg-type]

        tenant = await svc.create(
            TenantCreate(
                slug="pro-org", name="Pro", subscription_tier=SubscriptionTier.professional
            )
        )
        assert tenant.subscription_tier == "professional"

    async def test_defaults_to_starter_tier(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = TenantService(session)  # type: ignore[arg-type]

        tenant = await svc.create(TenantCreate(slug="s", name="S"))
        assert tenant.subscription_tier == "starter"


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


class TestGetTenant:
    async def test_returns_tenant_when_found(self) -> None:
        t = _make_tenant()
        session = _make_session(_scalar_result(t))
        svc = TenantService(session)  # type: ignore[arg-type]
        result = await svc.get(t.id)
        assert result is t

    async def test_raises_not_found_when_missing(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = TenantService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.get(uuid4())


# ---------------------------------------------------------------------------
# get_by_slug
# ---------------------------------------------------------------------------


class TestGetBySlug:
    async def test_returns_tenant(self) -> None:
        t = _make_tenant(slug="my-slug")
        session = _make_session(_scalar_result(t))
        svc = TenantService(session)  # type: ignore[arg-type]
        result = await svc.get_by_slug("my-slug")
        assert result.slug == "my-slug"

    async def test_raises_not_found(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = TenantService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.get_by_slug("ghost")


# ---------------------------------------------------------------------------
# list_tenants
# ---------------------------------------------------------------------------


class TestListTenants:
    async def test_returns_list(self) -> None:
        tenants = [_make_tenant(slug=f"org-{i}") for i in range(4)]
        session = _make_session(_scalars_result(tenants))
        svc = TenantService(session)  # type: ignore[arg-type]
        result = await svc.list_tenants()
        assert len(result) == 4

    async def test_returns_empty_list(self) -> None:
        session = _make_session(_scalars_result([]))
        svc = TenantService(session)  # type: ignore[arg-type]
        result = await svc.list_tenants()
        assert result == []


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


class TestUpdateTenant:
    async def test_updates_name(self) -> None:
        t = _make_tenant(name="old")
        session = _make_session(_scalar_result(t))
        svc = TenantService(session)  # type: ignore[arg-type]
        result = await svc.update(t.id, TenantUpdate(name="new"))
        assert result.name == "new"
        session.commit.assert_awaited_once()

    async def test_updates_subscription_tier(self) -> None:
        t = _make_tenant(subscription_tier="starter")
        session = _make_session(_scalar_result(t))
        svc = TenantService(session)  # type: ignore[arg-type]
        result = await svc.update(
            t.id, TenantUpdate(subscription_tier=SubscriptionTier.enterprise)
        )
        assert result.subscription_tier == "enterprise"

    async def test_deactivates_via_update(self) -> None:
        t = _make_tenant(is_active=True)
        session = _make_session(_scalar_result(t))
        svc = TenantService(session)  # type: ignore[arg-type]
        result = await svc.update(t.id, TenantUpdate(is_active=False))
        assert result.is_active is False

    async def test_none_fields_not_applied(self) -> None:
        t = _make_tenant(name="unchanged")
        session = _make_session(_scalar_result(t))
        svc = TenantService(session)  # type: ignore[arg-type]
        result = await svc.update(t.id, TenantUpdate())
        assert result.name == "unchanged"

    async def test_raises_not_found_when_missing(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = TenantService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.update(uuid4(), TenantUpdate(name="x"))


# ---------------------------------------------------------------------------
# deactivate / activate
# ---------------------------------------------------------------------------


class TestDeactivateActivate:
    async def test_deactivate_sets_inactive(self) -> None:
        t = _make_tenant(is_active=True)
        session = _make_session(_scalar_result(t))
        svc = TenantService(session)  # type: ignore[arg-type]
        await svc.deactivate(t.id)
        assert t.is_active is False
        session.commit.assert_awaited_once()

    async def test_deactivate_raises_not_found(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = TenantService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.deactivate(uuid4())

    async def test_activate_sets_active(self) -> None:
        t = _make_tenant(is_active=False)
        session = _make_session(_scalar_result(t))
        svc = TenantService(session)  # type: ignore[arg-type]
        result = await svc.activate(t.id)
        assert result.is_active is True
        session.commit.assert_awaited_once()

    async def test_activate_raises_not_found(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = TenantService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.activate(uuid4())
