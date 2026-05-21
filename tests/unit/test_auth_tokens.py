"""Module 4 — Auth: JWT token tests."""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from jose import jwt

from common.auth.tokens import TokenPayload, create_access_token, decode_access_token
from common.config import settings
from common.exceptions import AuthenticationError


@pytest.fixture()
def user_id() -> str:
    return str(uuid4())


@pytest.fixture()
def valid_token(user_id: str) -> str:
    return create_access_token(
        user_id=uuid4(),
        tenant_id="tenant-acme",
        role="operator",
    )


class TestCreateAccessToken:
    def test_returns_string(self) -> None:
        token = create_access_token(user_id=uuid4(), tenant_id="t", role="viewer")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_contains_three_jwt_segments(self) -> None:
        token = create_access_token(user_id=uuid4(), tenant_id="t", role="viewer")
        assert token.count(".") == 2

    def test_custom_expiry_respected(self) -> None:
        uid = uuid4()
        short = create_access_token(uid, "t", "viewer", timedelta(seconds=10))
        long = create_access_token(uid, "t", "viewer", timedelta(hours=24))
        s_raw = jwt.decode(short, settings.secret_key, algorithms=[settings.auth.algorithm])
        l_raw = jwt.decode(long, settings.secret_key, algorithms=[settings.auth.algorithm])
        assert l_raw["exp"] > s_raw["exp"]


class TestDecodeAccessToken:
    def test_decode_returns_token_payload(self, valid_token: str) -> None:
        payload = decode_access_token(valid_token)
        assert isinstance(payload, TokenPayload)

    def test_payload_contains_user_id(self) -> None:
        uid = uuid4()
        token = create_access_token(user_id=uid, tenant_id="t", role="admin")
        payload = decode_access_token(token)
        assert payload.sub == str(uid)

    def test_payload_contains_tenant_id(self) -> None:
        token = create_access_token(user_id=uuid4(), tenant_id="tenant-xyz", role="viewer")
        assert decode_access_token(token).tenant_id == "tenant-xyz"

    def test_payload_contains_role(self) -> None:
        token = create_access_token(user_id=uuid4(), tenant_id="t", role="agent")
        assert decode_access_token(token).role == "agent"

    def test_payload_exp_is_positive_integer(self, valid_token: str) -> None:
        payload = decode_access_token(valid_token)
        assert isinstance(payload.exp, int)
        assert payload.exp > 0

    def test_expired_token_raises_authentication_error(self) -> None:
        expired = create_access_token(
            user_id=uuid4(), tenant_id="t", role="viewer", expires_delta=timedelta(seconds=-1)
        )
        with pytest.raises(AuthenticationError):
            decode_access_token(expired)

    def test_tampered_signature_raises_authentication_error(self) -> None:
        token = create_access_token(user_id=uuid4(), tenant_id="t", role="viewer")
        last_char = token[-1]
        tampered = token[:-1] + ("b" if last_char != "b" else "c")
        with pytest.raises(AuthenticationError):
            decode_access_token(tampered)

    def test_wrong_key_raises_authentication_error(self) -> None:
        from datetime import UTC, datetime

        payload = {
            "sub": str(uuid4()),
            "tenant_id": "t",
            "role": "viewer",
            "exp": int((datetime.now(UTC) + timedelta(minutes=30)).timestamp()),
        }
        token_wrong_key = jwt.encode(payload, "wrong-secret", algorithm="HS256")
        with pytest.raises(AuthenticationError):
            decode_access_token(token_wrong_key)

    def test_arbitrary_string_raises_authentication_error(self) -> None:
        with pytest.raises(AuthenticationError):
            decode_access_token("not.a.token")

    def test_empty_string_raises_authentication_error(self) -> None:
        with pytest.raises(AuthenticationError):
            decode_access_token("")

    def test_round_trip_preserves_all_claims(self) -> None:
        uid = uuid4()
        token = create_access_token(uid, "tenant-round", "admin")
        payload = decode_access_token(token)
        assert payload.sub == str(uid)
        assert payload.tenant_id == "tenant-round"
        assert payload.role == "admin"
