"""Ingestion service FastAPI application."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from common.adapters import AdapterRegistry
from common.config import settings
from common.db import close_db, init_db

from .router import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
    app.state.registry = AdapterRegistry(settings)
    yield
    await app.state.registry.close()
    await close_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Dox Ingestion Service",
        description="Receives and persists CanonicalEvents from agent SDKs.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.get("/healthz", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
