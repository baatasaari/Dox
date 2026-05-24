"""Module 14 — User Management: service layer tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from common.exceptions import ConflictError, NotFoundError
from common.models.user import User
from common.schemas.enums import UserRole
from common.schemas.user import UserCreate, UserUpdate
from services.users.service import UserService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    *,
    email: str = "alice@example.com",
    tenant_id: str = "acme",
    role: str = UserRole.viewer,
    is_active: bool = True,
) -> User:
    return User(
        id=uuid4(),
        email=email,
        hashed_password="hashed",
        tenant_id=tenant_id,
        role=role,
        is_active=is_active,
    )


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


class TestCreateUser:
    async def test_creates_user_when_email_available(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = UserService(session)  # type: ignore[arg-type]

        with patch("services.users.service.hash_password", return_value="hashed"):
            user = await svc.create(
                UserCreate(
                    email="bob@example.com",
                    password="secret123",
                    tenant_id="acme",
                    role=UserRole.operator,
                )
            )

        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        assert user.email == "bob@example.com"
        assert user.tenant_id == "acme"
        assert user.role == "operator"

    async def test_raises_conflict_on_duplicate_email(self) -> None:
        existing = _make_user()
        session = _make_session(_scalar_result(existing))
        svc = UserService(session)  # type: ignore[arg-type]

        with pytest.raises(ConflictError):
            await svc.create(
                UserCreate(
                    email="alice@example.com",
                    password="secret123",
                    tenant_id="acme",
                )
            )

    async def test_password_is_hashed(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = UserService(session)  # type: ignore[arg-type]

        with patch("services.users.service.hash_password", return_value="bcrypt-hash") as mock_h:
            user = await svc.create(
                UserCreate(email="c@x.com", password="plaintext", tenant_id="t")
            )
            mock_h.assert_called_once_with("plaintext")
            assert user.hashed_password == "bcrypt-hash"

    async def test_defaults_role_to_viewer(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = UserService(session)  # type: ignore[arg-type]

        with patch("services.users.service.hash_password", return_value="h"):
            user = await svc.create(
                UserCreate(email="d@x.com", password="secret123", tenant_id="t")
            )
        assert user.role == "viewer"


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


class TestGetUser:
    async def test_returns_user_when_found(self) -> None:
        u = _make_user()
        session = _make_session(_scalar_result(u))
        svc = UserService(session)  # type: ignore[arg-type]
        result = await svc.get(u.id)
        assert result is u

    async def test_raises_not_found_when_missing(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = UserService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.get(uuid4())


# ---------------------------------------------------------------------------
# get_by_email
# ---------------------------------------------------------------------------


class TestGetByEmail:
    async def test_returns_user(self) -> None:
        u = _make_user(email="eve@example.com")
        session = _make_session(_scalar_result(u))
        svc = UserService(session)  # type: ignore[arg-type]
        result = await svc.get_by_email("eve@example.com")
        assert result.email == "eve@example.com"

    async def test_raises_not_found(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = UserService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.get_by_email("ghost@example.com")


# ---------------------------------------------------------------------------
# list_for_tenant
# ---------------------------------------------------------------------------


class TestListForTenant:
    async def test_returns_list(self) -> None:
        users = [_make_user(email=f"u{i}@x.com") for i in range(4)]
        session = _make_session(_scalars_result(users))
        svc = UserService(session)  # type: ignore[arg-type]
        result = await svc.list_for_tenant("acme")
        assert len(result) == 4

    async def test_returns_empty(self) -> None:
        session = _make_session(_scalars_result([]))
        svc = UserService(session)  # type: ignore[arg-type]
        assert await svc.list_for_tenant("no-tenant") == []


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


class TestUpdateUser:
    async def test_updates_role(self) -> None:
        u = _make_user(role=UserRole.viewer)
        session = _make_session(_scalar_result(u))
        svc = UserService(session)  # type: ignore[arg-type]
        result = await svc.update(u.id, UserUpdate(role=UserRole.admin))
        assert result.role == "admin"
        session.commit.assert_awaited_once()

    async def test_deactivates_via_update(self) -> None:
        u = _make_user(is_active=True)
        session = _make_session(_scalar_result(u))
        svc = UserService(session)  # type: ignore[arg-type]
        result = await svc.update(u.id, UserUpdate(is_active=False))
        assert result.is_active is False

    async def test_none_fields_not_applied(self) -> None:
        u = _make_user(role=UserRole.operator)
        session = _make_session(_scalar_result(u))
        svc = UserService(session)  # type: ignore[arg-type]
        result = await svc.update(u.id, UserUpdate())
        assert result.role == "operator"

    async def test_raises_not_found_when_missing(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = UserService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.update(uuid4(), UserUpdate(role=UserRole.admin))


# ---------------------------------------------------------------------------
# deactivate
# ---------------------------------------------------------------------------


class TestDeactivateUser:
    async def test_sets_inactive(self) -> None:
        u = _make_user(is_active=True)
        session = _make_session(_scalar_result(u))
        svc = UserService(session)  # type: ignore[arg-type]
        await svc.deactivate(u.id)
        assert u.is_active is False
        session.commit.assert_awaited_once()

    async def test_raises_not_found(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = UserService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.deactivate(uuid4())


# ---------------------------------------------------------------------------
# change_password
# ---------------------------------------------------------------------------


class TestChangePassword:
    async def test_updates_hashed_password(self) -> None:
        u = _make_user()
        session = _make_session(_scalar_result(u))
        svc = UserService(session)  # type: ignore[arg-type]

        with patch("services.users.service.hash_password", return_value="new-hash"):
            result = await svc.change_password(u.id, "newpassword")

        assert result.hashed_password == "new-hash"
        session.commit.assert_awaited_once()

    async def test_raises_not_found(self) -> None:
        session = _make_session(_scalar_result(None))
        svc = UserService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.change_password(uuid4(), "newpassword")

    async def test_password_is_hashed_not_stored_plain(self) -> None:
        u = _make_user()
        session = _make_session(_scalar_result(u))
        svc = UserService(session)  # type: ignore[arg-type]

        with patch("services.users.service.hash_password", return_value="hashed-new") as mh:
            await svc.change_password(u.id, "mynewpass")
            mh.assert_called_once_with("mynewpass")
