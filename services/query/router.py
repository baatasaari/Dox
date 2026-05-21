"""Query service HTTP routes — event retrieval and audit verification."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from common.exceptions import NotFoundError
from common.schemas.query import (
    EventFilter,
    EventSummary,
    IntegrityReportResponse,
    PaginatedEventsResponse,
    RecordIntegrityResponse,
)

from .deps import get_query_service
from .service import EventQueryService

router = APIRouter(tags=["events"])


@router.get("/v1/events", response_model=PaginatedEventsResponse)
async def list_events(
    tenant_id: str,
    service: Annotated[EventQueryService, Depends(get_query_service)],
    agent_id: Annotated[str | None, Query()] = None,
    event_type: Annotated[str | None, Query()] = None,
    environment: Annotated[str | None, Query()] = None,
    session_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedEventsResponse:
    from common.schemas.enums import Environment, EventType

    filters = EventFilter(
        tenant_id=tenant_id,
        agent_id=agent_id,
        event_type=EventType(event_type) if event_type else None,
        environment=Environment(environment) if environment else None,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )
    events = await service.list_events(filters)
    total = await service.count_events(filters)
    return PaginatedEventsResponse(
        events=[EventSummary.model_validate(e) for e in events],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/v1/events/{event_id}", response_model=EventSummary)
async def get_event(
    event_id: UUID,
    service: Annotated[EventQueryService, Depends(get_query_service)],
) -> EventSummary:
    try:
        record = await service.get_event(event_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return EventSummary.model_validate(record)


@router.get("/v1/audit/verify", response_model=IntegrityReportResponse)
async def verify_integrity(
    tenant_id: str,
    service: Annotated[EventQueryService, Depends(get_query_service)],
    limit: Annotated[int, Query(ge=1, le=10000)] = 1000,
) -> IntegrityReportResponse:
    report = await service.verify_integrity(tenant_id, limit=limit)
    return IntegrityReportResponse(
        tenant_id=report.tenant_id,
        total_checked=report.total_checked,
        passed=report.passed,
        failed=report.failed,
        is_clean=report.is_clean,
        records=[
            RecordIntegrityResponse(
                record_id=r.record_id,
                event_id=r.event_id,
                status=r.status,
                stored_hash=r.stored_hash,
                computed_hash=r.computed_hash,
            )
            for r in report.records
        ],
    )
