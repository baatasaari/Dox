"""Auth HTTP routes."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from common.schemas.auth import TokenRequest, TokenResponse

from .deps import get_auth_service
from .service import AuthService

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
async def get_token(
    request: TokenRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    user = await service.authenticate(request.email, request.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return service.create_token(user)
