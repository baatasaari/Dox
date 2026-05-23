"""Dox unified gateway — assembles all service routers into a single FastAPI application."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.api import add_exception_handlers
from common.auth.dependencies import require_role
from common.schemas.enums import UserRole
from services.audit.router import router as audit_log_router
from services.auth.router import router as auth_router
from services.compliance.router import router as compliance_router
from services.drift.router import router as drift_router
from services.ingestion.router import router as ingestion_router
from services.notify.router import router as notify_router
from services.policy.router import router as policy_router
from services.query.router import router as query_router
from services.quota.router import router as quota_router
from services.registry.router import router as registry_router
from services.sentinel.router import router as sentinel_router
from services.tenant.router import router as tenant_router
from services.users.router import router as users_router

# ---------------------------------------------------------------------------
# Role-access matrix: maps each router to its minimum required roles.
# auth_router is public (no entry here).
# ---------------------------------------------------------------------------
_ANY_AUTHENTICATED = [UserRole.agent, UserRole.viewer, UserRole.operator, UserRole.admin]
_OPERATOR_PLUS = [UserRole.operator, UserRole.admin]
_ADMIN_ONLY = [UserRole.admin]

_SECURED_ROUTERS = [
    # (router, allowed_roles)
    (audit_log_router, [UserRole.viewer, UserRole.operator, UserRole.admin]),
    (compliance_router, [UserRole.viewer, UserRole.operator, UserRole.admin]),
    (drift_router, [UserRole.viewer, UserRole.operator, UserRole.admin]),
    (ingestion_router, [UserRole.agent, UserRole.operator, UserRole.admin]),
    (notify_router, _OPERATOR_PLUS),
    (policy_router, _OPERATOR_PLUS),
    (query_router, [UserRole.viewer, UserRole.operator, UserRole.admin]),
    (quota_router, [UserRole.viewer, UserRole.operator, UserRole.admin]),
    (registry_router, _ANY_AUTHENTICATED),
    (sentinel_router, [UserRole.viewer, UserRole.operator, UserRole.admin]),
    (tenant_router, _ADMIN_ONLY),
    (users_router, _ADMIN_ONLY),
]

_DESCRIPTION = """\
**Dox** is a cloud-agnostic governance control plane for agentic AI systems.

It provides:
- Agent registry and lifecycle management
- Real-time event ingestion and drift detection
- Policy evaluation and sentinel alerting
- Quota enforcement and compliance reporting
- Webhook-based notification delivery
- Multi-tenant user management
"""


def create_app(*, cors_origins: list[str] | None = None) -> FastAPI:
    app = FastAPI(
        title="Dox — Agent Governance & Drift Observatory",
        description=_DESCRIPTION,
        version="0.1.0",
        contact={"name": "Dox Platform", "url": "https://github.com/baatasaari/dox"},
        license_info={"name": "Apache 2.0"},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins if cors_origins is not None else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    add_exception_handlers(app)

    # Auth endpoint is public — no JWT required.
    app.include_router(auth_router)

    # All other routers require a valid JWT with appropriate role.
    for router, roles in _SECURED_ROUTERS:
        app.include_router(router, dependencies=[require_role(*roles)])

    @app.get("/healthz", tags=["ops"], include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"], include_in_schema=False)
    async def ready() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
