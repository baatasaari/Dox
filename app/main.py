"""Dox unified gateway — assembles all service routers into a single FastAPI application."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.api import add_exception_handlers
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

_ROUTERS = [
    auth_router,
    compliance_router,
    drift_router,
    ingestion_router,
    notify_router,
    policy_router,
    query_router,
    quota_router,
    registry_router,
    sentinel_router,
    tenant_router,
    users_router,
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

    for router in _ROUTERS:
        app.include_router(router)

    @app.get("/healthz", tags=["ops"], include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"], include_in_schema=False)
    async def ready() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
