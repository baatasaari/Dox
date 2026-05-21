"""FastAPI dependency providers for the ingestion service."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from common.adapters import AdapterRegistry
from common.db import get_session
from services.sentinel.deps import get_sentinel_service
from services.sentinel.service import SentinelService

from .service import IngestionService


def get_registry(request: Request) -> AdapterRegistry:
    registry: AdapterRegistry = request.app.state.registry
    return registry


async def get_ingestion_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    registry: Annotated[AdapterRegistry, Depends(get_registry)],
    sentinel: Annotated[SentinelService, Depends(get_sentinel_service)],
) -> IngestionService:
    return IngestionService(
        session=session,
        event_bus=registry.event_bus,
        metrics=registry.metrics,
        sentinel_service=sentinel,
    )
