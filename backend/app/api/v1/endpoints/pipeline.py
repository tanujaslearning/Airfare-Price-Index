"""Data pipeline on-demand execution REST API endpoints."""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.api_responses import (
    PipelineTriggerRequest,
    PipelineTriggerResponse,
)
from backend.app.services.pipeline_service import run_daily_live_pipeline_trigger

logger = logging.getLogger("apix.api.pipeline")
router = APIRouter(prefix="/pipeline", tags=["Pipeline"])


@router.post(
    "/trigger",
    response_model=PipelineTriggerResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger Daily LIVE Route-Window Collection Pipeline",
    description="Triggers the approved daily LIVE route-window workflow. It does not use the obsolete single-cell pipeline.",
)
async def trigger_pipeline(
    payload: Optional[PipelineTriggerRequest] = None,
    db: Session = Depends(get_db),
) -> PipelineTriggerResponse:
    """Executes the approved daily LIVE matrix workflow."""
    req = payload or PipelineTriggerRequest()
    logger.info(
        "Triggering data pipeline: collection_date=%s, random_seed=%s, force_recalculate=%s",
        req.collection_date, req.random_seed, req.force_recalculate,
    )

    summary = await run_daily_live_pipeline_trigger(
        db=db,
        collection_date=req.collection_date,
    )

    return PipelineTriggerResponse(**summary)
