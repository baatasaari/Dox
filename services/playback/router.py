"""Session Playback HTTP routes.

Endpoints
---------
POST   /v1/playback                          Create a replay from an existing session
GET    /v1/playback                          List replays for a tenant
GET    /v1/playback/{replay_id}             Get a specific replay
GET    /v1/playback/{replay_id}/frames      Get the ordered frame index
GET    /v1/playback/{replay_id}/state/{n}   Reconstruct state at position n
POST   /v1/playback/{replay_id}/step        Advance replay by one frame
POST   /v1/playback/{replay_id}/run         Execute the full replay workflow
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from common.schemas.replay import (
    AccumulatedState,
    ReplayFrame,
    ReplayFrameListResponse,
    ReplayListResponse,
    SessionReplayCreate,
    SessionReplayResponse,
)

from .deps import get_playback_service
from .service import PlaybackService

router = APIRouter(prefix="/v1/playback", tags=["playback"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SessionReplayResponse,
    summary="Create a replay index for an existing session",
)
async def create_replay(
    body: SessionReplayCreate,
    svc: Annotated[PlaybackService, Depends(get_playback_service)],
) -> SessionReplayResponse:
    replay = await svc.create(body)
    return SessionReplayResponse.model_validate(replay)


@router.get(
    "",
    response_model=ReplayListResponse,
    summary="List session replays for a tenant",
)
async def list_replays(
    tenant_id: str,
    svc: Annotated[PlaybackService, Depends(get_playback_service)],
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ReplayListResponse:
    replays = await svc.list_for_tenant(
        tenant_id, status=status_filter, limit=limit, offset=offset
    )
    return ReplayListResponse(
        replays=[SessionReplayResponse.model_validate(r) for r in replays],
        total=len(replays),
    )


@router.get(
    "/{replay_id}",
    response_model=SessionReplayResponse,
    summary="Get a session replay by ID",
)
async def get_replay(
    replay_id: UUID,
    svc: Annotated[PlaybackService, Depends(get_playback_service)],
) -> SessionReplayResponse:
    replay = await svc.get(replay_id)
    return SessionReplayResponse.model_validate(replay)


@router.get(
    "/{replay_id}/frames",
    response_model=ReplayFrameListResponse,
    summary="List ordered frames for a replay",
)
async def get_frames(
    replay_id: UUID,
    svc: Annotated[PlaybackService, Depends(get_playback_service)],
) -> ReplayFrameListResponse:
    frames = await svc.get_frames(replay_id)
    return ReplayFrameListResponse(
        replay_id=replay_id, frames=frames, total=len(frames)
    )


@router.get(
    "/{replay_id}/state/{position}",
    response_model=AccumulatedState,
    summary="Reconstruct agent state at a given frame position",
)
async def get_state_at(
    replay_id: UUID,
    position: int,
    svc: Annotated[PlaybackService, Depends(get_playback_service)],
) -> AccumulatedState:
    return await svc.get_state_at(replay_id, position)


@router.post(
    "/{replay_id}/step",
    response_model=ReplayFrame | None,
    summary="Advance the replay by one frame",
)
async def step_replay(
    replay_id: UUID,
    svc: Annotated[PlaybackService, Depends(get_playback_service)],
) -> ReplayFrame | None:
    return await svc.step(replay_id)


@router.post(
    "/{replay_id}/run",
    response_model=SessionReplayResponse,
    summary="Execute the full replay workflow (LangGraph)",
)
async def run_replay(
    replay_id: UUID,
    svc: Annotated[PlaybackService, Depends(get_playback_service)],
) -> SessionReplayResponse:
    replay = await svc.run(replay_id)
    return SessionReplayResponse.model_validate(replay)
