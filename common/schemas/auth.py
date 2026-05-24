"""Auth request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseModel):
    sub: str
    tenant_id: str
    role: str
    exp: int
