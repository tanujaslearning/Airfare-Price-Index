"""Read-only provenance and live-observation reporting endpoints."""

from datetime import date as dt_date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.provenance import (
    LiveQuotesResponse,
    LiveSummaryResponse,
    ProvenanceJobsResponse,
    ProvenanceSummaryResponse,
)
from backend.app.services.provenance_service import (
    live_quotes,
    live_summary,
    provenance_jobs,
    provenance_summary,
    resolve_route,
    resolve_source,
)

router = APIRouter(prefix="/provenance", tags=["Provenance"])


@router.get(
    "/summary",
    response_model=ProvenanceSummaryResponse,
    summary="Get raw quote provenance summary",
)
def get_provenance_summary(db: Session = Depends(get_db)) -> ProvenanceSummaryResponse:
    """Returns raw quote counts grouped by collection mode, source, and job."""
    return ProvenanceSummaryResponse(data=provenance_summary(db))


@router.get(
    "/live-summary",
    response_model=LiveSummaryResponse,
    summary="Get live-only aggregate fare summary",
)
def get_live_summary(
    route_code: Optional[str] = Query(None, description="Route filter, e.g. DEL-BOM or DELBOM"),
    advance_window_days: Optional[int] = Query(None, ge=0),
    source: Optional[str] = Query(None, description="Airline/source code or name, e.g. QP or Akasa Air"),
    collection_date: Optional[dt_date] = Query(None),
    db: Session = Depends(get_db),
) -> LiveSummaryResponse:
    """Returns live-only aggregates and never infers live status from source or flight number."""
    route = _resolve_route_or_error(db, route_code)
    airline = _resolve_source_or_error(db, source)
    return LiveSummaryResponse(
        data=live_summary(
            db,
            route=route,
            source=airline,
            advance_window_days=advance_window_days,
            collection_date=collection_date,
        )
    )


@router.get(
    "/jobs",
    response_model=ProvenanceJobsResponse,
    summary="Get collection job provenance",
)
def get_provenance_jobs(db: Session = Depends(get_db)) -> ProvenanceJobsResponse:
    """Returns completed and failed jobs with synthetic/live mode visible."""
    return ProvenanceJobsResponse(data=provenance_jobs(db))


@router.get(
    "/live-quotes",
    response_model=LiveQuotesResponse,
    summary="Get paginated live-only raw quotes",
)
def get_live_quotes(
    route: Optional[str] = Query(None, description="Route filter, e.g. DEL-BOM or DELBOM"),
    source: Optional[str] = Query(None, description="Airline/source code or name, e.g. QP or Akasa Air"),
    advance_window_days: Optional[int] = Query(None, ge=0),
    collection_date: Optional[dt_date] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> LiveQuotesResponse:
    """Returns only raw quotes explicitly marked collection_mode=LIVE."""
    route_obj = _resolve_route_or_error(db, route)
    airline = _resolve_source_or_error(db, source)
    total, items = live_quotes(
        db,
        route=route_obj,
        source=airline,
        advance_window_days=advance_window_days,
        collection_date=collection_date,
        limit=limit,
        offset=offset,
    )
    return LiveQuotesResponse(total=total, limit=limit, offset=offset, data=items)


def _resolve_route_or_error(db: Session, route_code: Optional[str]):
    try:
        route = resolve_route(db, route_code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if route_code is not None and route is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Route '{route_code}' not found.")
    return route


def _resolve_source_or_error(db: Session, source: Optional[str]):
    try:
        airline = resolve_source(db, source)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if source is not None and airline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source '{source}' not found.")
    return airline
