"""Dashboard filter metadata endpoints."""

from typing import List, Tuple

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.airline import Airline
from backend.app.models.quote import RawAirfareQuote
from backend.app.models.route import Route
from backend.app.schemas.api_responses import FilterOption, FilterOptionsResponse
from backend.app.schemas.index import CollectionMode

router = APIRouter(prefix="/filters", tags=["Filters"])


@router.get(
    "/options",
    response_model=FilterOptionsResponse,
    summary="Get dashboard filter options",
    description="Returns read-only filter options derived from configured routes and persisted quote provenance.",
)
def get_filter_options(
    collection_mode: CollectionMode = Query("LIVE", description="Observation provenance mode: LIVE or MOCK"),
    active_only: bool = Query(True, description="Limit route-derived options to active routes"),
    db: Session = Depends(get_db),
) -> FilterOptionsResponse:
    """Returns filter values without creating or modifying observations."""
    routes_query = db.query(Route)
    if active_only:
        routes_query = routes_query.filter(Route.is_active == True)
    routes = routes_query.all()

    origins = _route_count_options(
        db,
        collection_mode=collection_mode,
        values=sorted({route.origin_code for route in routes}),
        column=Route.origin_code,
    )
    destinations = _route_count_options(
        db,
        collection_mode=collection_mode,
        values=sorted({route.destination_code for route in routes}),
        column=Route.destination_code,
    )

    airline_rows = (
        db.query(
            Airline.code,
            Airline.name,
            func.count(RawAirfareQuote.id).label("quote_count"),
        )
        .join(RawAirfareQuote, RawAirfareQuote.source_id == Airline.id)
        .filter(RawAirfareQuote.collection_mode == collection_mode)
        .group_by(Airline.code, Airline.name)
        .order_by(Airline.name.asc())
        .all()
    )
    airlines = [
        FilterOption(value=row.code, label=row.name, quote_count=int(row.quote_count))
        for row in airline_rows
    ]

    periods = [
        FilterOption(value="all", label="All"),
        FilterOption(value="7", label="Last 7"),
        FilterOption(value="30", label="Last 30"),
    ]

    return FilterOptionsResponse(
        collection_mode=collection_mode,
        origins=origins,
        destinations=destinations,
        airlines=airlines,
        periods=periods,
    )


def _route_count_options(
    db: Session,
    collection_mode: CollectionMode,
    values: List[str],
    column,
) -> List[FilterOption]:
    counts: List[Tuple[str, int]] = (
        db.query(column, func.count(RawAirfareQuote.id).label("quote_count"))
        .join(Route, RawAirfareQuote.route_id == Route.id)
        .filter(RawAirfareQuote.collection_mode == collection_mode)
        .group_by(column)
        .all()
    )
    count_by_value = {value: int(count) for value, count in counts}
    return [
        FilterOption(value=value, label=value, quote_count=count_by_value.get(value, 0))
        for value in values
    ]
