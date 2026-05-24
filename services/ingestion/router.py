"""Ingestion HTTP routes."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from common.schemas.events import CanonicalEvent

from .deps import get_ingestion_service
from .schemas import BatchIngestRequest, BatchIngestResponse, IngestResponse
from .service import IngestionService

router = APIRouter(prefix="/v1/events", tags=["ingestion"])


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=IngestResponse)
async def ingest_event(
    event: CanonicalEvent,
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
) -> IngestResponse:
    record = await service.ingest(event)
    return IngestResponse(event_id=record.event_id)


@router.post(
    "/batch",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestResponse,
)
async def ingest_batch(
    request: BatchIngestRequest,
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
) -> BatchIngestResponse:
    records = await service.ingest_batch(request.events)
    return BatchIngestResponse(
        accepted=len(records),
        event_ids=[r.event_id for r in records],
    )
