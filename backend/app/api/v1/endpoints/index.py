"""Airfare Price Index REST API endpoints."""

import logging
from datetime import date as dt_date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.index_value import AirfareIndexValue
from backend.app.schemas.api_responses import IndexLatestResponse, IndexHistoricalResponse
from backend.app.schemas.index import AirfareIndexValueRead, CollectionMode, LiveIndexResponse
from backend.app.services.live_index_service import calculate_live_only_index
from backend.app.services.provenance_service import resolve_route, resolve_source

logger = logging.getLogger("apix.api.index")
router = APIRouter(prefix="/index", tags=["Index"])


@router.get(
    "/live",
    response_model=LiveIndexResponse,
    summary="Get non-persisted LIVE-only airfare index analysis",
    description="Calculates live-only index analysis from raw provenance without modifying the persisted mixed-data index.",
)
def get_live_index(
    collection_date: Optional[dt_date] = Query(None, description="Collection date to evaluate; defaults to latest LIVE date"),
    route_code: Optional[str] = Query(None, description="Optional route filter, e.g. DEL-BOM or DELBOM"),
    origin: Optional[str] = Query(None, min_length=3, max_length=3, description="Optional origin airport filter, e.g. DEL"),
    destination: Optional[str] = Query(None, min_length=3, max_length=3, description="Optional destination airport filter, e.g. BOM"),
    advance_window_days: Optional[int] = Query(None, ge=0, description="Optional advance window filter"),
    source: Optional[str] = Query(None, description="Optional source code/name filter, e.g. QP or Akasa Air"),
    db: Session = Depends(get_db),
) -> LiveIndexResponse:
    """Returns ad-hoc live-only analysis; no AirfareIndexValue row is created or updated."""
    try:
        route = resolve_route(db, route_code)
        airline = resolve_source(db, source)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    if route_code is not None and route is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Route '{route_code}' not found.")
    if source is not None and airline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source '{source}' not found.")

    return calculate_live_only_index(
        db,
        collection_date=collection_date,
        route=route,
        origin_code=origin,
        destination_code=destination,
        advance_window_days=advance_window_days,
        source=airline,
    )


@router.get(
    "/latest",
    response_model=IndexLatestResponse,
    summary="Get Latest National Composite Airfare Price Index",
    description="Returns the most recent calculated APIx index score, Day-over-Day percentage change, 7-day MA, and 30-day MA.",
)
def get_latest_index(
    frequency: str = Query("daily", description="Aggregation granularity: daily, weekly, or monthly"),
    collection_mode: CollectionMode = Query("LIVE", description="Observation provenance mode: LIVE or MOCK"),
    db: Session = Depends(get_db),
) -> IndexLatestResponse:
    """Retrieves the latest available national composite index value."""
    latest = (
        db.query(AirfareIndexValue)
        .filter(
            AirfareIndexValue.frequency == frequency,
            AirfareIndexValue.collection_mode == collection_mode,
        )
        .order_by(AirfareIndexValue.date.desc())
        .first()
    )

    if not latest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {collection_mode} index records found for frequency '{frequency}'. Trigger the matching pipeline before requesting this mode.",
        )

    return IndexLatestResponse(
        date=latest.date,
        frequency=latest.frequency,
        collection_mode=latest.collection_mode,
        index_value=latest.index_value,
        baseline_period=latest.baseline_period,
        ma_7d=latest.ma_7d,
        ma_30d=latest.ma_30d,
        dod_change_pct=latest.dod_change_pct,
        calculated_at=latest.calculated_at,
    )


@router.get(
    "/historical",
    response_model=IndexHistoricalResponse,
    summary="Get Historical Time-Series Index Values",
    description="Returns historical time-series of national composite APIx index records with optional date range filters.",
)
def get_historical_index(
    start_date: Optional[dt_date] = Query(None, description="Start date (YYYY-MM-DD) inclusive"),
    end_date: Optional[dt_date] = Query(None, description="End date (YYYY-MM-DD) inclusive"),
    frequency: str = Query("daily", description="Interval granularity (daily, weekly, monthly)"),
    collection_mode: CollectionMode = Query("LIVE", description="Observation provenance mode: LIVE or MOCK"),
    limit: int = Query(100, ge=1, le=1000, description="Max number of records to return"),
    db: Session = Depends(get_db),
) -> IndexHistoricalResponse:
    """Returns chronological time-series index data for analytical charting and tables."""
    query = db.query(AirfareIndexValue).filter(
        AirfareIndexValue.frequency == frequency,
        AirfareIndexValue.collection_mode == collection_mode,
    )

    if start_date:
        query = query.filter(AirfareIndexValue.date >= start_date)
    if end_date:
        query = query.filter(AirfareIndexValue.date <= end_date)

    records = query.order_by(AirfareIndexValue.date.asc()).limit(limit).all()

    items = [
        AirfareIndexValueRead.model_validate(r)
        for r in records
    ]

    return IndexHistoricalResponse(
        count=len(items),
        frequency=frequency,
        collection_mode=collection_mode,
        start_date=start_date,
        end_date=end_date,
        items=items,
    )
