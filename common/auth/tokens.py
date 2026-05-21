"""JWT creation and decoding."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from jose import JWTError, jwt
from pydantic import BaseModel

from common.config import settings
from common.exceptions import AuthenticationError


class TokenPayload(BaseModel):
    sub: str
    tenant_id: str
    role: str
    exp: int


def create_access_token(
    user_id: UUID,
    tenant_id: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta
        or timedelta(minutes=settings.auth.access_token_expire_minutes)
    )
    payload = {
        "sub": str(user_id),
        "tenant_id": tenant_id,
        "role": role,
        "exp": int(expire.timestamp()),
    }
    return str(jwt.encode(payload, settings.secret_key, algorithm=settings.auth.algorithm))


def decode_access_token(token: str) -> TokenPayload:
    try:
        raw = jwt.decode(
            token, settings.secret_key, algorithms=[settings.auth.algorithm]
        )
        return TokenPayload(**raw)
    except (JWTError, Exception) as exc:
        raise AuthenticationError(f"Invalid or expired token: {exc}") from exc
