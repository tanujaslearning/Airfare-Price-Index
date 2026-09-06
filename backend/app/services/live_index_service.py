"""Ad-hoc LIVE-only Airfare Price Index analytics."""

from datetime import date
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.data.route_basket import APPROVED_ADVANCE_WINDOWS
from backend.app.models.airline import Airline
from backend.app.models.quote import ProcessedAirfareQuote, RawAirfareQuote
from backend.app.models.route import Route
from backend.app.schemas.index import (
    LiveIndexCoverage,
    LiveIndexResponse,
    LiveIndexRouteValue,
    LiveIndexWindowValue,
)
from backend.app.services.collection_dates import collection_date_from_timestamp, collection_day_bounds_utc
from backend.app.services.dgca_route_weights import weight_by_route_code
from backend.app.services.fare_reference_service import live_reference_fare_map
from backend.app.services.ingestion_service import COLLECTION_MODE_LIVE

LIVE_INDEX_SUFFICIENT_COVERAGE_PCT = 100.0


def calculate_live_only_index(
    db: Session,
    collection_date: Optional[date] = None,
    route: Optional[Route] = None,
    origin_code: Optional[str] = None,
    destination_code: Optional[str] = None,
    advance_window_days: Optional[int] = None,
    source: Optional[Airline] = None,
) -> LiveIndexResponse:
    """Calculates a non-persisted live-only index using the existing index math.

    The calculation filters raw quote provenance to collection_mode=LIVE before
    aggregation. Route/window sub-indices require fixed observed-reference fares;
    missing reference data is reported explicitly and never replaced with 100.
    """
    c_date = collection_date or _latest_live_collection_date(db)
    reference_status, reference_fares = live_reference_fare_map(db)
    expected_routes = _expected_routes(db, route, origin_code, destination_code)
    active_routes = _expected_routes(db, None, None, None)
    expected_windows = [advance_window_days] if advance_window_days is not None else list(APPROVED_ADVANCE_WINDOWS)
    expected_combinations = len(expected_routes) * len(expected_windows)

    window_values = _live_window_values(
        db,
        collection_date=c_date,
        route=route,
        origin_code=origin_code,
        destination_code=destination_code,
        advance_window_days=advance_window_days,
        source=source,
        reference_fares=reference_fares,
    )
    observed_keys = {
        (value.route, value.advance_window_days)
        for value in window_values
        if value.route in {r.route_key for r in expected_routes} and value.advance_window_days in expected_windows
    }
    observed_combinations = len(observed_keys)
    coverage_pct = round((observed_combinations / expected_combinations) * 100.0, 2) if expected_combinations else 0.0
    has_reference_values = all(value.sub_index is not None for value in window_values)
    is_sufficient = (
        expected_combinations > 0
        and observed_combinations == expected_combinations
        and reference_status.is_available
        and has_reference_values
    )

    route_values = _route_values(window_values, expected_routes, expected_windows, active_routes)
    sources_used = sorted({source_name for value in window_values for source_name in value.sources_used})
    live_quote_count = sum(value.quote_count for value in window_values)

    index_value = None
    if is_sufficient and route_values:
        weighted_route_values = [
            route_value for route_value in route_values if route_value.dgca_weight is not None and route_value.dgca_weight > 0
        ]
        total_weight = sum(route_value.dgca_weight or 0.0 for route_value in weighted_route_values)
        if total_weight > 0:
            index_value = round(
                float(
                    sum((route_value.dgca_weight or 0.0) * (route_value.route_index or 0.0) for route_value in weighted_route_values)
                    / total_weight
                ),
                2,
            )

    return LiveIndexResponse(
        status="SUFFICIENT_COVERAGE" if is_sufficient else "INSUFFICIENT_COVERAGE",
        collection_date=c_date,
        index_value=index_value,
        index_scope="FILTERED" if route or origin_code or destination_code or advance_window_days is not None or source else "NATIONAL",
        coverage=LiveIndexCoverage(
            expected_route_window_combinations=expected_combinations,
            observed_route_window_combinations=observed_combinations,
            coverage_pct=coverage_pct,
            minimum_required_coverage_pct=LIVE_INDEX_SUFFICIENT_COVERAGE_PCT,
            is_sufficient=is_sufficient,
        ),
        live_quote_count=live_quote_count,
        routes_represented=len({value.route for value in window_values}),
        advance_windows_represented=len({value.advance_window_days for value in window_values}),
        sources_represented=sources_used,
        route_values=route_values,
        reference_status=reference_status.status,
        reference_period=reference_status.period,
        reference_message=reference_status.message,
    )


def _latest_live_collection_date(db: Session) -> Optional[date]:
    row = (
        db.query(RawAirfareQuote.scraped_at)
        .filter(RawAirfareQuote.collection_mode == COLLECTION_MODE_LIVE)
        .order_by(RawAirfareQuote.scraped_at.desc())
        .first()
    )
    return collection_date_from_timestamp(row.scraped_at) if row and row.scraped_at else None


def _expected_routes(
    db: Session,
    route: Optional[Route],
    origin_code: Optional[str],
    destination_code: Optional[str],
) -> List[Route]:
    if route is not None:
        return [route]
    query = db.query(Route).filter(Route.is_active == True)
    if origin_code:
        query = query.filter(Route.origin_code == origin_code.upper())
    if destination_code:
        query = query.filter(Route.destination_code == destination_code.upper())
    return query.order_by(Route.id.asc()).all()


def _live_window_values(
    db: Session,
    collection_date: Optional[date],
    route: Optional[Route],
    origin_code: Optional[str],
    destination_code: Optional[str],
    advance_window_days: Optional[int],
    source: Optional[Airline],
    reference_fares: Dict[Tuple[str, int], float],
) -> List[LiveIndexWindowValue]:
    if collection_date is None:
        return []

    start, end = collection_day_bounds_utc(collection_date)
    query = (
        db.query(
            Route.origin_code,
            Route.destination_code,
            ProcessedAirfareQuote.advance_window_days,
            func.count(ProcessedAirfareQuote.id).label("quote_count"),
            func.avg(ProcessedAirfareQuote.clean_total_fare).label("mean_fare"),
        )
        .join(RawAirfareQuote, ProcessedAirfareQuote.raw_quote_id == RawAirfareQuote.id)
        .join(Route, RawAirfareQuote.route_id == Route.id)
        .filter(
            RawAirfareQuote.collection_mode == COLLECTION_MODE_LIVE,
            ProcessedAirfareQuote.is_outlier == False,
            RawAirfareQuote.scraped_at >= start,
            RawAirfareQuote.scraped_at < end,
        )
    )
    if route is not None:
        query = query.filter(RawAirfareQuote.route_id == route.id)
    elif origin_code or destination_code:
        if origin_code:
            query = query.filter(Route.origin_code == origin_code.upper())
        if destination_code:
            query = query.filter(Route.destination_code == destination_code.upper())
    if advance_window_days is not None:
        query = query.filter(ProcessedAirfareQuote.advance_window_days == advance_window_days)
    if source is not None:
        query = query.filter(RawAirfareQuote.source_id == source.id)

    rows = (
        query.group_by(Route.origin_code, Route.destination_code, ProcessedAirfareQuote.advance_window_days)
        .order_by(Route.origin_code, Route.destination_code, ProcessedAirfareQuote.advance_window_days)
        .all()
    )
    sources_by_key = _sources_by_route_window(
        db,
        collection_date,
        route,
        origin_code,
        destination_code,
        advance_window_days,
        source,
    )

    values: List[LiveIndexWindowValue] = []
    for row in rows:
        route_key = f"{row.origin_code}-{row.destination_code}"
        window = int(row.advance_window_days)
        baseline = reference_fares.get((route_key, window))
        mean_fare = round(float(row.mean_fare), 2)
        sub_index = round((mean_fare / baseline) * 100.0, 2) if baseline and baseline > 0 else None
        values.append(
            LiveIndexWindowValue(
                route=route_key,
                advance_window_days=window,
                quote_count=int(row.quote_count),
                mean_fare=mean_fare,
                baseline_fare=baseline,
                sub_index=sub_index,
                sources_used=sources_by_key.get((route_key, window), []),
            )
        )
    return values


def _sources_by_route_window(
    db: Session,
    collection_date: date,
    route: Optional[Route],
    origin_code: Optional[str],
    destination_code: Optional[str],
    advance_window_days: Optional[int],
    source: Optional[Airline],
) -> Dict[Tuple[str, int], List[str]]:
    start, end = collection_day_bounds_utc(collection_date)
    query = (
        db.query(
            Route.origin_code,
            Route.destination_code,
            ProcessedAirfareQuote.advance_window_days,
            Airline.name,
        )
        .join(RawAirfareQuote, ProcessedAirfareQuote.raw_quote_id == RawAirfareQuote.id)
        .join(Route, RawAirfareQuote.route_id == Route.id)
        .outerjoin(Airline, RawAirfareQuote.source_id == Airline.id)
        .filter(
            RawAirfareQuote.collection_mode == COLLECTION_MODE_LIVE,
            ProcessedAirfareQuote.is_outlier == False,
            RawAirfareQuote.scraped_at >= start,
            RawAirfareQuote.scraped_at < end,
        )
        .distinct()
    )
    if route is not None:
        query = query.filter(RawAirfareQuote.route_id == route.id)
    elif origin_code or destination_code:
        if origin_code:
            query = query.filter(Route.origin_code == origin_code.upper())
        if destination_code:
            query = query.filter(Route.destination_code == destination_code.upper())
    if advance_window_days is not None:
        query = query.filter(ProcessedAirfareQuote.advance_window_days == advance_window_days)
    if source is not None:
        query = query.filter(RawAirfareQuote.source_id == source.id)

    sources: Dict[Tuple[str, int], Set[str]] = {}
    for row in query.all():
        route_key = f"{row.origin_code}-{row.destination_code}"
        key = (route_key, int(row.advance_window_days))
        sources.setdefault(key, set()).add(row.name or "UNKNOWN")
    return {key: sorted(names) for key, names in sources.items()}


def _route_values(
    window_values: List[LiveIndexWindowValue],
    expected_routes: List[Route],
    expected_windows: List[int],
    normalization_routes: List[Route],
) -> List[LiveIndexRouteValue]:
    route_by_key = {route.route_key: route for route in expected_routes}
    route_weights = weight_by_route_code(expected_routes, normalization_routes=normalization_routes)
    grouped: Dict[str, List[LiveIndexWindowValue]] = {}
    for value in window_values:
        if value.route not in route_by_key or value.advance_window_days not in expected_windows or value.sub_index is None:
            continue
        grouped.setdefault(value.route, []).append(value)

    route_values: List[LiveIndexRouteValue] = []
    for route_key, values in sorted(grouped.items()):
        route = route_by_key[route_key]
        route_weight = route_weights.get(route_key)
        route_values.append(
            LiveIndexRouteValue(
                route=route_key,
                route_index=round(float(np.mean([value.sub_index for value in values if value.sub_index is not None])), 2),
                dgca_weight=route_weight,
                quote_count=sum(value.quote_count for value in values),
                windows_observed=len(values),
                window_values=values,
            )
        )
    return route_values
