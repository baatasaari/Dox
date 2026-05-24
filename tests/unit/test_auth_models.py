"""Module 4 — Auth: User and Tenant model tests."""
from __future__ import annotations

from uuid import UUID, uuid4

from common.auth.passwords import hash_password
from common.models.tenant import Tenant
from common.models.user import User


class TestUserModel:
    def test_user_construction(self) -> None:
        user = User(
            id=uuid4(),
            email="alice@example.com",
            hashed_password=hash_password("secret"),
            tenant_id="tenant-1",
            role="operator",
        )
        assert user.email == "alice@example.com"
        assert user.tenant_id == "tenant-1"
        assert user.role == "operator"

    def test_id_is_uuid(self) -> None:
        uid = uuid4()
        user = User(
            id=uid,
            email="b@b.com",
            hashed_password="h",
            tenant_id="t",
            role="viewer",
        )
        assert user.id == uid
        assert isinstance(user.id, UUID)

    def test_is_active_defaults_to_true(self) -> None:
        user = User(
            id=uuid4(),
            email="c@c.com",
            hashed_password="h",
            tenant_id="t",
            role="viewer",
        )
        assert user.is_active is True

    def test_hashed_password_differs_from_plain(self) -> None:
        user = User(
            id=uuid4(),
            email="d@d.com",
            hashed_password=hash_password("plain"),
            tenant_id="t",
            role="viewer",
        )
        assert user.hashed_password != "plain"

    def test_two_users_can_have_same_tenant(self) -> None:
        u1 = User(
            id=uuid4(), email="e1@e.com", hashed_password="h", tenant_id="same", role="viewer"
        )
        u2 = User(
            id=uuid4(), email="e2@e.com", hashed_password="h", tenant_id="same", role="viewer"
        )
        assert u1.tenant_id == u2.tenant_id


class TestTenantModel:
    def test_tenant_construction(self) -> None:
        tenant = Tenant(
            id=uuid4(),
            slug="acme",
            name="ACME Corp",
        )
        assert tenant.slug == "acme"
        assert tenant.name == "ACME Corp"

    def test_id_is_uuid(self) -> None:
        tid = uuid4()
        tenant = Tenant(id=tid, slug="t", name="T")
        assert tenant.id == tid
        assert isinstance(tenant.id, UUID)

    def test_subscription_tier_defaults_to_starter(self) -> None:
        tenant = Tenant(id=uuid4(), slug="s", name="S")
        assert tenant.subscription_tier == "starter"

    def test_is_active_defaults_to_true(self) -> None:
        tenant = Tenant(id=uuid4(), slug="a", name="A")
        assert tenant.is_active is True

    def test_custom_subscription_tier(self) -> None:
        tenant = Tenant(
            id=uuid4(), slug="ent", name="Enterprise Co", subscription_tier="enterprise"
        )
        assert tenant.subscription_tier == "enterprise"
