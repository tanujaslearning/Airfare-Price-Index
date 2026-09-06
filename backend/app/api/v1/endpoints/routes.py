"""DGCA Monitored Routes and Route-Level Airfare Index REST API endpoints."""

import logging
from datetime import date as dt_date, datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.data.route_basket import APPROVED_ADVANCE_WINDOWS
from backend.app.db.session import get_db
from backend.app.models.route import Route
from backend.app.models.quote import ProcessedAirfareQuote, RawAirfareQuote
from backend.app.models.index_value import AirfareIndexValue
from backend.app.schemas.api_responses import (
    RouteDetailResponse,
    RouteCorridorIndexResponse,
    RouteWindowBreakdown,
    RouteWeightsResponse,
)
from backend.app.schemas.index import CollectionMode
from backend.app.services.collection_dates import collection_date_from_timestamp, collection_day_bounds_utc
from backend.app.services.dgca_route_weights import calculate_dgca_route_weights, weight_by_route_code
from backend.app.services.fare_reference_service import live_reference_fare_map
from backend.app.services.index_engine import get_route_baseline_fare
from backend.app.services.provenance_service import resolve_source

logger = logging.getLogger("apix.api.routes")
router = APIRouter(prefix="/routes", tags=["Routes"])


def _find_route(db: Session, route_code: str) -> Optional[Route]:
    """Helper to locate a route by route_key (DEL-BOM), concatenated code (DELBOM), or ID."""
    clean = route_code.strip().upper()
    if "-" in clean:
        parts = clean.split("-")
        if len(parts) == 2:
            route = db.query(Route).filter(
                Route.origin_code == parts[0],
                Route.destination_code == parts[1],
            ).first()
            if route:
                return route
    elif len(clean) == 6:
        route = db.query(Route).filter(
            Route.origin_code == clean[:3],
            Route.destination_code == clean[3:],
        ).first()
        if route:
            return route

    if clean.isdigit():
        route = db.query(Route).filter(Route.id == int(clean)).first()
        if route:
            return route

    # Fallback to direct route_key match
    return db.query(Route).filter(
        (Route.origin_code + "-" + Route.destination_code) == clean
    ).first()


def _route_window_breakdown(
    route: Route,
    quotes: List[ProcessedAirfareQuote],
    *,
    include_missing_baseline: bool = True,
    collection_mode: str = "MOCK",
    live_reference_fares: Optional[Dict[Tuple[str, int], float]] = None,
) -> tuple[List[RouteWindowBreakdown], Optional[float]]:
    """Calculates one route's window metrics from already-scoped quotes."""
    windows: List[RouteWindowBreakdown] = []
    observed_sub_indices: List[float] = []

    for window in APPROVED_ADVANCE_WINDOWS:
        window_quotes = [quote for quote in quotes if quote.advance_window_days == window]
        baseline_fare = (
            (live_reference_fares or {}).get((route.route_key, window))
            if collection_mode == "LIVE"
            else get_route_baseline_fare(route.route_key, window)
        )

        if window_quotes:
            mean_fare = round(float(np.mean([quote.clean_total_fare for quote in window_quotes])), 2)
            sub_index = round((mean_fare / baseline_fare) * 100.0, 2) if baseline_fare and baseline_fare > 0 else None
            quotes_count = len(window_quotes)
            if sub_index is not None:
                observed_sub_indices.append(sub_index)
        else:
            if not include_missing_baseline:
                continue
            mean_fare = baseline_fare or 0.0
            sub_index = 100.0 if baseline_fare else None
            quotes_count = 0

        windows.append(
            RouteWindowBreakdown(
                advance_window_days=window,
                window_label=f"T+{window}",
                mean_fare=mean_fare,
                baseline_fare=baseline_fare,
                sub_index=sub_index,
                quotes_count=quotes_count,
            )
        )

    route_index = round(float(np.mean(observed_sub_indices)), 2) if observed_sub_indices else None
    return windows, route_index


@router.get(
    "",
    response_model=List[RouteDetailResponse],
    summary="Get Monitored DGCA Routes",
    description="Returns all monitored DGCA city-pair flight corridors with distance and passenger traffic weights.",
)
def get_routes(
    active_only: bool = Query(True, description="Filter to active scraping routes"),
    db: Session = Depends(get_db),
) -> List[RouteDetailResponse]:
    """Retrieves all monitored DGCA routes."""
    query = db.query(Route)
    if active_only:
        query = query.filter(Route.is_active == True)

    routes = query.order_by(Route.id.asc()).all()
    weights = weight_by_route_code(routes)
    responses: List[RouteDetailResponse] = []
    for route in routes:
        official_weight = weights.get(route.route_key)
        responses.append(
            RouteDetailResponse(
                id=route.id,
                route_key=route.route_key,
                route_code=route.route_key,
                origin_code=route.origin_code,
                destination_code=route.destination_code,
                origin=route.origin,
                destination=route.destination,
                distance_km=route.distance_km,
                distance=route.distance,
                dgca_weight=official_weight,
                passenger_market_weight=official_weight,
                is_active=route.is_active,
            )
        )
    return responses


@router.get(
    "/weights",
    response_model=RouteWeightsResponse,
    summary="Get DGCA Route Passenger Weights",
    description="Returns official DGCA passenger-traffic route weights and mapping coverage for active APIx routes.",
)
def get_route_weights(
    active_only: bool = Query(True, description="Filter to active scraping routes"),
    db: Session = Depends(get_db),
) -> RouteWeightsResponse:
    """Retrieves DGCA passenger-traffic route weights without mutating database state."""
    query = db.query(Route)
    if active_only:
        query = query.filter(Route.is_active == True)

    routes = query.order_by(Route.id.asc()).all()
    return RouteWeightsResponse(**calculate_dgca_route_weights(routes))


@router.get(
    "/{route_code}/index",
    response_model=RouteCorridorIndexResponse,
    summary="Get Route-Specific Airfare Index and Advance Window Breakdown",
    description="Returns the sub-index and advance-purchase pricing curve (T+1, T+7, T+15, T+30, T+45) for a selected route.",
)
def get_route_index(
    route_code: str,
    target_date: Optional[dt_date] = Query(None, description="Date for route evaluation (YYYY-MM-DD)"),
    collection_mode: CollectionMode = Query("LIVE", description="Observation provenance mode: LIVE or MOCK"),
    source: Optional[str] = Query(None, description="Optional airline/source code or name, e.g. QP or Akasa Air"),
    db: Session = Depends(get_db),
) -> RouteCorridorIndexResponse:
    """Calculates route-level sub-index and advance purchase window breakdown."""
    route = _find_route(db, route_code)
    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route '{route_code}' not found.",
        )

    try:
        airline = resolve_source(db, source)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if source is not None and airline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source '{source}' not found.")

    # Determine target evaluation date
    if target_date is not None:
        eval_date = target_date
    else:
        # Resolve latest available collection date for this route.
        latest_raw = (
            db.query(RawAirfareQuote)
            .join(ProcessedAirfareQuote, ProcessedAirfareQuote.raw_quote_id == RawAirfareQuote.id)
            .filter(RawAirfareQuote.route_id == route.id)
            .filter(ProcessedAirfareQuote.is_outlier == False)
            .filter(RawAirfareQuote.collection_mode == collection_mode)
            .filter(RawAirfareQuote.source_id == airline.id if airline is not None else True)
            .order_by(RawAirfareQuote.scraped_at.desc())
            .first()
        )
        if latest_raw and latest_raw.scraped_at:
            eval_date = collection_date_from_timestamp(latest_raw.scraped_at)
        else:
            latest_idx = (
                db.query(AirfareIndexValue)
                .filter(AirfareIndexValue.collection_mode == collection_mode)
                .order_by(AirfareIndexValue.date.desc())
                .first()
            )
            if latest_idx:
                eval_date = latest_idx.date
            else:
                eval_date = datetime.now(timezone.utc).date()

    start_dt, end_dt = collection_day_bounds_utc(eval_date)

    # Query clean processed quotes for this route collected on eval_date
    quotes = (
        db.query(ProcessedAirfareQuote)
        .join(RawAirfareQuote, ProcessedAirfareQuote.raw_quote_id == RawAirfareQuote.id)
        .filter(
            ProcessedAirfareQuote.route_id == route.id,
            ProcessedAirfareQuote.is_outlier == False,
            RawAirfareQuote.scraped_at >= start_dt,
            RawAirfareQuote.scraped_at < end_dt,
            RawAirfareQuote.collection_mode == collection_mode,
            RawAirfareQuote.source_id == airline.id if airline is not None else True,
        )
        .all()
    )

    if not quotes:
        if target_date is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No {collection_mode} fare quotes found for route '{route.route_key}' on {eval_date}.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No {collection_mode} fare quotes found for route '{route.route_key}'. Trigger the matching pipeline first.",
            )

    include_missing_baseline = collection_mode == "MOCK"
    _, live_reference_fares = live_reference_fare_map(db) if collection_mode == "LIVE" else (None, {})
    windows, route_index = _route_window_breakdown(
        route,
        quotes,
        include_missing_baseline=include_missing_baseline,
        collection_mode=collection_mode,
        live_reference_fares=live_reference_fares,
    )

    # Collect historical points across distinct collection dates for this route.
    historical_points: List[Dict[str, Any]] = []
    try:
        historical_raw = (
            db.query(RawAirfareQuote.scraped_at)
            .join(ProcessedAirfareQuote, ProcessedAirfareQuote.raw_quote_id == RawAirfareQuote.id)
            .filter(
                ProcessedAirfareQuote.route_id == route.id,
                ProcessedAirfareQuote.is_outlier == False,
                RawAirfareQuote.collection_mode == collection_mode,
                RawAirfareQuote.source_id == airline.id if airline is not None else True,
            )
            .order_by(RawAirfareQuote.scraped_at.asc())
            .all()
        )
        distinct_dates = sorted({collection_date_from_timestamp(row.scraped_at) for row in historical_raw if row.scraped_at})[-30:]
        for collection_day in distinct_dates:
            day_start, day_end = collection_day_bounds_utc(collection_day)
            day_quotes = (
                db.query(ProcessedAirfareQuote)
                .join(RawAirfareQuote, ProcessedAirfareQuote.raw_quote_id == RawAirfareQuote.id)
                .filter(
                    ProcessedAirfareQuote.route_id == route.id,
                    ProcessedAirfareQuote.is_outlier == False,
                    RawAirfareQuote.scraped_at >= day_start,
                    RawAirfareQuote.scraped_at < day_end,
                    RawAirfareQuote.collection_mode == collection_mode,
                    RawAirfareQuote.source_id == airline.id if airline is not None else True,
                )
                .all()
            )
            if day_quotes:
                _, day_route_index = _route_window_breakdown(
                    route,
                    day_quotes,
                    include_missing_baseline=include_missing_baseline,
                    collection_mode=collection_mode,
                    live_reference_fares=live_reference_fares,
                )
                historical_points.append({"date": str(collection_day), "route_index": day_route_index})
    except Exception as exc:
        logger.debug("Failed querying distinct historical dates: %s", exc)

    if not historical_points:
        historical_points = [{"date": str(eval_date), "route_index": route_index}]

    active_routes = db.query(Route).filter(Route.is_active == True).all()
    dgca_weight = weight_by_route_code([route], normalization_routes=active_routes).get(route.route_key)

    return RouteCorridorIndexResponse(
        route_key=route.route_key,
        route_code=route.route_key,
        origin=route.origin,
        origin_code=route.origin_code,
        destination=route.destination,
        destination_code=route.destination_code,
        distance=route.distance,
        distance_km=route.distance_km,
        passenger_market_weight=dgca_weight,
        dgca_weight=dgca_weight,
        collection_mode=collection_mode,
        target_date=eval_date,
        route_index=route_index,
        windows=windows,
        historical_points=historical_points,
    )
