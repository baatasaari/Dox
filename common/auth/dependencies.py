"""FastAPI security dependencies — JWT authentication and role-based authorisation."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from common.auth.tokens import TokenPayload, decode_access_token
from common.exceptions import AuthenticationError, AuthorizationError
from common.schemas.enums import UserRole

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> TokenPayload:
    """Decode and validate a Bearer JWT; raises AuthenticationError on failure."""
    if credentials is None:
        raise AuthenticationError("Missing bearer token")
    return decode_access_token(credentials.credentials)


def require_role(*roles: UserRole) -> Any:
    """Return a FastAPI Depends that allows only the given roles.

    Usage::

        @router.post("/alerts", dependencies=[require_role(UserRole.admin, UserRole.operator)])
        async def create_alert(...): ...

        # or at router level:
        router = APIRouter(dependencies=[require_role(UserRole.admin)])
    """
    allowed = frozenset(str(r) for r in roles)

    async def _check(
        payload: Annotated[TokenPayload, Depends(get_current_user)],
    ) -> TokenPayload:
        if payload.role not in allowed:
            raise AuthorizationError(
                f"Role '{payload.role}' is not authorised for this operation; "
                f"required: {sorted(allowed)}"
            )
        return payload

    return Depends(_check)
