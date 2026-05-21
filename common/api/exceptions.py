"""Global exception handlers — maps DoxException subclasses to HTTP responses."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from common.exceptions import (
    AuthenticationError,
    AuthorizationError,
    DoxException,
    NotFoundError,
    RateLimitError,
    ValidationError,
)


def _error_body(exc: DoxException) -> dict[str, str]:
    return {"error": exc.code, "detail": exc.detail}


def add_exception_handlers(app: FastAPI) -> None:
    """Register DoxException → HTTP status-code mappings on *app*."""

    @app.exception_handler(NotFoundError)
    async def _not_found(_req: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content=_error_body(exc))

    @app.exception_handler(AuthenticationError)
    async def _auth_error(_req: Request, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content=_error_body(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(AuthorizationError)
    async def _authz_error(_req: Request, exc: AuthorizationError) -> JSONResponse:
        return JSONResponse(status_code=403, content=_error_body(exc))

    @app.exception_handler(ValidationError)
    async def _validation_error(_req: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content=_error_body(exc))

    @app.exception_handler(RateLimitError)
    async def _rate_limit(_req: Request, exc: RateLimitError) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content=_error_body(exc),
            headers={"Retry-After": str(exc.retry_after)},
        )

    @app.exception_handler(DoxException)
    async def _generic_dox(_req: Request, exc: DoxException) -> JSONResponse:
        return JSONResponse(status_code=400, content=_error_body(exc))
