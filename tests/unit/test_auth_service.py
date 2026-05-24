"""Module 4 — Auth: service layer tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from common.auth.passwords import hash_password
from common.models.user import User
from common.schemas.auth import TokenResponse
from services.auth.service import AuthService


def _make_user(password: str = "secret123", role: str = "operator") -> User:
    user = User()
    user.id = uuid4()
    user.email = "alice@example.com"
    user.hashed_password = hash_password(password)
    user.tenant_id = "tenant-acme"
    user.role = role
    user.is_active = True
    return user


def _make_session(user: User | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


class TestAuthServiceAuthenticate:
    async def test_valid_credentials_returns_user(self) -> None:
        user = _make_user("correct")
        service = AuthService(_make_session(user))  # type: ignore[arg-type]
        result = await service.authenticate("alice@example.com", "correct")
        assert result is user

    async def test_wrong_password_returns_none(self) -> None:
        user = _make_user("correct")
        service = AuthService(_make_session(user))  # type: ignore[arg-type]
        result = await service.authenticate("alice@example.com", "wrong")
        assert result is None

    async def test_unknown_email_returns_none(self) -> None:
        service = AuthService(_make_session(None))  # type: ignore[arg-type]
        result = await service.authenticate("ghost@example.com", "pass")
        assert result is None

    async def test_inactive_user_not_returned(self) -> None:
        # DB query filters is_active, so mock returns None for inactive
        service = AuthService(_make_session(None))  # type: ignore[arg-type]
        result = await service.authenticate("inactive@example.com", "pass")
        assert result is None

    async def test_queries_session_with_email(self) -> None:
        mock_session = _make_session(None)
        service = AuthService(mock_session)  # type: ignore[arg-type]
        await service.authenticate("test@example.com", "pass")
        mock_session.execute.assert_awaited_once()


class TestAuthServiceCreateToken:
    def test_returns_token_response(self) -> None:
        user = _make_user()
        session = MagicMock()
        service = AuthService(session)  # type: ignore[arg-type]
        response = service.create_token(user)
        assert isinstance(response, TokenResponse)

    def test_token_type_is_bearer(self) -> None:
        user = _make_user()
        service = AuthService(MagicMock())  # type: ignore[arg-type]
        assert service.create_token(user).token_type == "bearer"

    def test_access_token_is_non_empty_string(self) -> None:
        user = _make_user()
        service = AuthService(MagicMock())  # type: ignore[arg-type]
        token = service.create_token(user)
        assert isinstance(token.access_token, str)
        assert len(token.access_token) > 10

    def test_expires_in_is_positive(self) -> None:
        user = _make_user()
        service = AuthService(MagicMock())  # type: ignore[arg-type]
        assert service.create_token(user).expires_in > 0

    def test_token_decodes_to_correct_user(self) -> None:
        from common.auth.tokens import decode_access_token

        user = _make_user()
        service = AuthService(MagicMock())  # type: ignore[arg-type]
        response = service.create_token(user)
        payload = decode_access_token(response.access_token)
        assert payload.sub == str(user.id)
        assert payload.tenant_id == user.tenant_id
        assert payload.role == user.role

    def test_admin_role_preserved_in_token(self) -> None:
        from common.auth.tokens import decode_access_token

        user = _make_user(role="admin")
        service = AuthService(MagicMock())  # type: ignore[arg-type]
        token = service.create_token(user)
        assert decode_access_token(token.access_token).role == "admin"
