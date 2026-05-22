"""Integration: UserService business logic with real model instances."""
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


def _session_for_get(user: User | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _session_for_create(existing: User | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _session_with_list(users: list[User]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = users
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# User creation
# ---------------------------------------------------------------------------


class TestUserCreation:
    async def test_create_new_user_succeeds(self) -> None:
        session = _session_for_create(None)
        svc = UserService(session)  # type: ignore[arg-type]

        with patch("services.users.service.hash_password", return_value="bcrypt"):
            user = await svc.create(
                UserCreate(
                    email="new@example.com",
                    password="secret123",
                    tenant_id="acme",
                    role=UserRole.operator,
                )
            )

        assert user.email == "new@example.com"
        assert user.tenant_id == "acme"
        assert user.role == "operator"
        assert user.hashed_password == "bcrypt"
        assert user.is_active is True

    async def test_duplicate_email_raises_conflict(self) -> None:
        existing = _make_user(email="taken@example.com")
        session = _session_for_create(existing)
        svc = UserService(session)  # type: ignore[arg-type]

        with patch("services.users.service.hash_password", return_value="h"):
            with pytest.raises(ConflictError):
                await svc.create(
                    UserCreate(
                        email="taken@example.com",
                        password="secret123",
                        tenant_id="acme",
                    )
                )

    async def test_viewer_is_default_role(self) -> None:
        session = _session_for_create(None)
        svc = UserService(session)  # type: ignore[arg-type]

        with patch("services.users.service.hash_password", return_value="h"):
            user = await svc.create(
                UserCreate(email="v@x.com", password="secret123", tenant_id="t")
            )
        assert user.role == "viewer"

    async def test_password_never_stored_in_plain(self) -> None:
        session = _session_for_create(None)
        svc = UserService(session)  # type: ignore[arg-type]

        with patch("services.users.service.hash_password", return_value="hashed") as mh:
            user = await svc.create(
                UserCreate(email="p@x.com", password="myplainpass", tenant_id="t")
            )
            mh.assert_called_once_with("myplainpass")
        assert user.hashed_password != "myplainpass"


# ---------------------------------------------------------------------------
# User lookup
# ---------------------------------------------------------------------------


class TestUserLookup:
    async def test_get_by_id_returns_correct_user(self) -> None:
        u = _make_user()
        session = _session_for_get(u)
        svc = UserService(session)  # type: ignore[arg-type]
        result = await svc.get(u.id)
        assert result.id == u.id

    async def test_get_missing_id_raises_not_found(self) -> None:
        session = _session_for_get(None)
        svc = UserService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.get(uuid4())

    async def test_get_by_email_returns_user(self) -> None:
        u = _make_user(email="find@me.com")
        session = _session_for_get(u)
        svc = UserService(session)  # type: ignore[arg-type]
        result = await svc.get_by_email("find@me.com")
        assert result.email == "find@me.com"

    async def test_get_by_email_missing_raises_not_found(self) -> None:
        session = _session_for_get(None)
        svc = UserService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.get_by_email("ghost@nowhere.com")


# ---------------------------------------------------------------------------
# User listing
# ---------------------------------------------------------------------------


class TestUserListing:
    async def test_list_returns_all_for_tenant(self) -> None:
        users = [_make_user(email=f"u{i}@x.com") for i in range(6)]
        session = _session_with_list(users)
        svc = UserService(session)  # type: ignore[arg-type]
        result = await svc.list_for_tenant("acme")
        assert len(result) == 6

    async def test_list_empty_tenant_returns_empty(self) -> None:
        session = _session_with_list([])
        svc = UserService(session)  # type: ignore[arg-type]
        assert await svc.list_for_tenant("ghost-tenant") == []


# ---------------------------------------------------------------------------
# User update
# ---------------------------------------------------------------------------


class TestUserUpdate:
    async def test_promote_to_admin(self) -> None:
        u = _make_user(role=UserRole.viewer)
        session = _session_for_get(u)
        svc = UserService(session)  # type: ignore[arg-type]
        result = await svc.update(u.id, UserUpdate(role=UserRole.admin))
        assert result.role == "admin"

    async def test_deactivate_user(self) -> None:
        u = _make_user(is_active=True)
        session = _session_for_get(u)
        svc = UserService(session)  # type: ignore[arg-type]
        result = await svc.update(u.id, UserUpdate(is_active=False))
        assert result.is_active is False

    async def test_empty_update_is_noop(self) -> None:
        u = _make_user(role=UserRole.operator)
        session = _session_for_get(u)
        svc = UserService(session)  # type: ignore[arg-type]
        result = await svc.update(u.id, UserUpdate())
        assert result.role == "operator"

    async def test_update_missing_raises_not_found(self) -> None:
        session = _session_for_get(None)
        svc = UserService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.update(uuid4(), UserUpdate(role=UserRole.admin))


# ---------------------------------------------------------------------------
# Deactivate
# ---------------------------------------------------------------------------


class TestDeactivate:
    async def test_deactivate_sets_inactive(self) -> None:
        u = _make_user(is_active=True)
        session = _session_for_get(u)
        svc = UserService(session)  # type: ignore[arg-type]
        await svc.deactivate(u.id)
        assert u.is_active is False
        session.commit.assert_awaited_once()

    async def test_deactivate_missing_raises_not_found(self) -> None:
        session = _session_for_get(None)
        svc = UserService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.deactivate(uuid4())


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------


class TestChangePassword:
    async def test_password_changed_and_hashed(self) -> None:
        u = _make_user()
        session = _session_for_get(u)
        svc = UserService(session)  # type: ignore[arg-type]

        with patch("services.users.service.hash_password", return_value="updated-hash"):
            result = await svc.change_password(u.id, "newpassword")

        assert result.hashed_password == "updated-hash"
        session.commit.assert_awaited_once()

    async def test_change_password_missing_raises_not_found(self) -> None:
        session = _session_for_get(None)
        svc = UserService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await svc.change_password(uuid4(), "newpass")

    async def test_successive_password_changes(self) -> None:
        u = _make_user()
        results = [MagicMock(), MagicMock()]
        results[0].scalar_one_or_none.return_value = u
        results[1].scalar_one_or_none.return_value = u
        session = MagicMock()
        session.execute = AsyncMock(side_effect=results)
        session.add = MagicMock()
        session.commit = AsyncMock()
        svc = UserService(session)  # type: ignore[arg-type]

        with patch("services.users.service.hash_password", side_effect=["hash1", "hash2"]):
            await svc.change_password(u.id, "pass1")
            assert u.hashed_password == "hash1"
            await svc.change_password(u.id, "pass2")
            assert u.hashed_password == "hash2"
