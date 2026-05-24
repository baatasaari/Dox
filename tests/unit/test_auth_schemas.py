"""Module 4 — Auth: schema tests."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from common.schemas.auth import TokenPayload, TokenRequest, TokenResponse


class TestTokenRequest:
    def test_valid_request(self) -> None:
        req = TokenRequest(email="user@example.com", password="s3cr3t")
        assert req.email == "user@example.com"
        assert req.password == "s3cr3t"

    def test_empty_email_raises(self) -> None:
        with pytest.raises(ValidationError):
            TokenRequest(email="", password="abc")

    def test_empty_password_raises(self) -> None:
        with pytest.raises(ValidationError):
            TokenRequest(email="user@example.com", password="")

    def test_missing_email_raises(self) -> None:
        with pytest.raises(ValidationError):
            TokenRequest(password="abc")  # type: ignore[call-arg]

    def test_missing_password_raises(self) -> None:
        with pytest.raises(ValidationError):
            TokenRequest(email="user@example.com")  # type: ignore[call-arg]


class TestTokenResponse:
    def test_token_type_defaults_to_bearer(self) -> None:
        r = TokenResponse(access_token="tok", expires_in=1800)
        assert r.token_type == "bearer"

    def test_required_fields(self) -> None:
        r = TokenResponse(access_token="tok.tok.tok", expires_in=1800)
        assert r.access_token == "tok.tok.tok"
        assert r.expires_in == 1800

    def test_missing_access_token_raises(self) -> None:
        with pytest.raises(ValidationError):
            TokenResponse(expires_in=1800)  # type: ignore[call-arg]


class TestTokenPayload:
    def test_all_fields(self) -> None:
        p = TokenPayload(sub="user-id", tenant_id="t1", role="admin", exp=9999999999)
        assert p.sub == "user-id"
        assert p.tenant_id == "t1"
        assert p.role == "admin"
        assert p.exp == 9999999999


class TestUserRoleEnum:
    def test_has_four_values(self) -> None:
        from common.schemas.enums import UserRole

        assert len(UserRole) == 4

    def test_contains_expected_roles(self) -> None:
        from common.schemas.enums import UserRole

        assert set(r.value for r in UserRole) == {"admin", "operator", "viewer", "agent"}


class TestSubscriptionTierEnum:
    def test_has_three_values(self) -> None:
        from common.schemas.enums import SubscriptionTier

        assert len(SubscriptionTier) == 3

    def test_contains_expected_tiers(self) -> None:
        from common.schemas.enums import SubscriptionTier

        assert set(t.value for t in SubscriptionTier) == {
            "starter",
            "professional",
            "enterprise",
        }
