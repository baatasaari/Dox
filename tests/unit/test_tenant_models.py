"""Module 12 — Tenant Management: model tests."""
from __future__ import annotations

from uuid import uuid4

from common.models.tenant import Tenant


def _make_tenant(**kw: object) -> Tenant:
    kw.setdefault("slug", "acme")
    kw.setdefault("name", "Acme Corp")
    return Tenant(**kw)  # type: ignore[arg-type]


class TestTenantDefaults:
    def test_is_active_defaults_true(self) -> None:
        t = _make_tenant()
        assert t.is_active is True

    def test_subscription_tier_defaults_starter(self) -> None:
        t = _make_tenant()
        assert t.subscription_tier == "starter"


class TestTenantFields:
    def test_stores_slug(self) -> None:
        t = _make_tenant(slug="my-org")
        assert t.slug == "my-org"

    def test_stores_name(self) -> None:
        t = _make_tenant(name="My Org")
        assert t.name == "My Org"

    def test_stores_subscription_tier(self) -> None:
        t = _make_tenant(subscription_tier="professional")
        assert t.subscription_tier == "professional"

    def test_explicit_is_active_false(self) -> None:
        t = _make_tenant(is_active=False)
        assert t.is_active is False

    def test_stores_id_when_provided(self) -> None:
        uid = uuid4()
        t = _make_tenant(id=uid)
        assert t.id == uid
