"""Prototype airfare reference-period calculations.

This module intentionally distinguishes the official CPI index reference
metadata from APIx's prototype observed-fare reference inputs.
"""

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.data.route_basket import APPROVED_ADVANCE_WINDOWS, DEFAULT_ROUTE_BASELINES
from backend.app.models.quote import ProcessedAirfareQuote, RawAirfareQuote
from backend.app.models.route import Route
from backend.app.services.collection_dates import collection_day_bounds_utc
from backend.app.services.ingestion_service import COLLECTION_MODE_LIVE

WINDOW_BASE_MULTIPLIERS: Dict[int, float] = {
    1: 1.75,
    7: 1.35,
    15: 1.12,
    30: 1.00,
    45: 0.90,
}

OFFICIAL_CPI_INDEX_REFERENCE = "2024 = 100"
OFFICIAL_CPI_PRICE_REFERENCE_PERIOD = "calendar year 2024"
OFFICIAL_CPI_WEIGHT_REFERENCE_PERIOD = "HCES 2023-24"

PROTOTYPE_REFERENCE_METHOD = "OBSERVED_LIVE_FIXED_REFERENCE_PERIOD"
PROTOTYPE_REFERENCE_COLLECTION_DATE = settings.PROTOTYPE_REFERENCE_COLLECTION_DATE
PROTOTYPE_REFERENCE_START_DATE = PROTOTYPE_REFERENCE_COLLECTION_DATE
PROTOTYPE_REFERENCE_END_DATE = PROTOTYPE_REFERENCE_COLLECTION_DATE
PROTOTYPE_REFERENCE_PERIOD_LABEL = f"observed LIVE fixed reference period {PROTOTYPE_REFERENCE_COLLECTION_DATE.isoformat()}"
PROTOTYPE_REFERENCE_REQUIRED_COVERAGE_PCT = 100.0


def prototype_reference_collection_date() -> date:
    """Returns the configured fixed LIVE reference collection date."""
    return settings.PROTOTYPE_REFERENCE_COLLECTION_DATE


def prototype_reference_period_label() -> str:
    """Returns a display label for the configured LIVE reference period."""
    return f"observed LIVE fixed reference period {prototype_reference_collection_date().isoformat()}"


@dataclass(frozen=True)
class ReferenceStatus:
    """Availability state for the fixed observed LIVE reference period."""

    status: str
    period: str
    expected_route_window_combinations: int
    observed_route_window_combinations: int
    message: str

    @property
    def is_available(self) -> bool:
        return self.status == "AVAILABLE"


@dataclass(frozen=True)
class ReferenceCompleteness:
    """Read-only route/window completeness report for a designated reference date."""

    reference_date: date
    expected_cells: int
    valid_live_cells: int
    missing_cells: List[str]
    complete: bool

    @property
    def status(self) -> str:
        return "COMPLETE" if self.complete else "INCOMPLETE"


def legacy_assumption_reference_fare(route_key: str, advance_window_days: int) -> float:
    """Returns the old assumed rupee reference used only for MOCK/dev compatibility."""
    base_cost = DEFAULT_ROUTE_BASELINES.get(route_key, 4000.0)
    multiplier = WINDOW_BASE_MULTIPLIERS.get(advance_window_days, 1.0)
    raw_base = base_cost * multiplier
    total_base = raw_base + (raw_base * 0.21) + 650.0
    return round(total_base, 2)


def live_reference_status(db: Session) -> ReferenceStatus:
    """Checks whether the fixed LIVE reference period has complete route/window coverage."""
    completeness = validate_live_reference_completeness(db, prototype_reference_collection_date())
    period_label = prototype_reference_period_label()
    if completeness.expected_cells == 0:
        return ReferenceStatus(
            status="INSUFFICIENT_REFERENCE_DATA",
            period=period_label,
            expected_route_window_combinations=0,
            observed_route_window_combinations=0,
            message="No active routes are configured for the prototype reference basket.",
        )

    if completeness.complete:
        return ReferenceStatus(
            status="AVAILABLE",
            period=period_label,
            expected_route_window_combinations=completeness.expected_cells,
            observed_route_window_combinations=completeness.valid_live_cells,
            message="Fixed observed LIVE reference period is complete.",
        )
    return ReferenceStatus(
        status="INSUFFICIENT_REFERENCE_DATA",
        period=period_label,
        expected_route_window_combinations=completeness.expected_cells,
        observed_route_window_combinations=completeness.valid_live_cells,
        message=(
            "Fixed observed LIVE reference period is incomplete; route/window "
            "reference fares are unavailable until all expected cells are represented."
        ),
    )


def validate_live_reference_completeness(
    db: Session,
    reference_date: Optional[date] = None,
) -> ReferenceCompleteness:
    """Reports whether all active route/window cells have valid LIVE observations.

    A cell is counted only from non-outlier processed quotes linked to raw
    observations explicitly marked collection_mode=LIVE and collected on the
    designated local collection date.
    """
    ref_date = reference_date or prototype_reference_collection_date()
    active_routes = db.query(Route).filter(Route.is_active == True).order_by(Route.id.asc()).all()
    expected_keys = [
        (route.id, route.route_key, window)
        for route in active_routes
        for window in APPROVED_ADVANCE_WINDOWS
    ]
    if not expected_keys:
        return ReferenceCompleteness(
            reference_date=ref_date,
            expected_cells=0,
            valid_live_cells=0,
            missing_cells=[],
            complete=False,
        )

    start, end = collection_day_bounds_utc(ref_date)
    rows = (
        db.query(ProcessedAirfareQuote.route_id, ProcessedAirfareQuote.advance_window_days)
        .join(RawAirfareQuote, ProcessedAirfareQuote.raw_quote_id == RawAirfareQuote.id)
        .filter(
            RawAirfareQuote.collection_mode == COLLECTION_MODE_LIVE,
            RawAirfareQuote.scraped_at >= start,
            RawAirfareQuote.scraped_at < end,
            RawAirfareQuote.total_fare > 0,
            ProcessedAirfareQuote.clean_total_fare > 0,
            ProcessedAirfareQuote.is_outlier == False,
            ProcessedAirfareQuote.route_id.in_([route.id for route in active_routes]),
            ProcessedAirfareQuote.advance_window_days.in_(APPROVED_ADVANCE_WINDOWS),
        )
        .distinct()
        .all()
    )
    observed = {(int(route_id), int(window)) for route_id, window in rows}
    missing_cells = [
        f"{route_key}:T+{window}"
        for route_id, route_key, window in expected_keys
        if (route_id, window) not in observed
    ]
    return ReferenceCompleteness(
        reference_date=ref_date,
        expected_cells=len(expected_keys),
        valid_live_cells=len(observed),
        missing_cells=missing_cells,
        complete=not missing_cells,
    )


def live_reference_fare_map(db: Session) -> Tuple[ReferenceStatus, Dict[Tuple[str, int], float]]:
    """Returns route/window LIVE reference fares when the fixed reference period is complete."""
    status = live_reference_status(db)
    if not status.is_available:
        return status, {}

    reference_date = prototype_reference_collection_date()
    start, end = collection_day_bounds_utc(reference_date)
    rows = (
        db.query(
            Route.origin_code,
            Route.destination_code,
            ProcessedAirfareQuote.advance_window_days,
            func.avg(ProcessedAirfareQuote.clean_total_fare).label("reference_fare"),
        )
        .join(RawAirfareQuote, ProcessedAirfareQuote.raw_quote_id == RawAirfareQuote.id)
        .join(Route, ProcessedAirfareQuote.route_id == Route.id)
        .filter(
            RawAirfareQuote.collection_mode == COLLECTION_MODE_LIVE,
            RawAirfareQuote.scraped_at >= start,
            RawAirfareQuote.scraped_at < end,
            ProcessedAirfareQuote.is_outlier == False,
            ProcessedAirfareQuote.advance_window_days.in_(APPROVED_ADVANCE_WINDOWS),
            Route.is_active == True,
        )
        .group_by(Route.origin_code, Route.destination_code, ProcessedAirfareQuote.advance_window_days)
        .all()
    )
    references = {
        (f"{row.origin_code}-{row.destination_code}", int(row.advance_window_days)): round(float(row.reference_fare), 2)
        for row in rows
        if row.reference_fare is not None and float(row.reference_fare) > 0
    }
    return status, references


def reference_fare_for_mode(
    db: Session,
    *,
    collection_mode: str,
    route_key: str,
    advance_window_days: int,
) -> Optional[float]:
    """Returns a reference fare for an index mode without fabricating missing LIVE references."""
    mode = collection_mode.upper()
    if mode == COLLECTION_MODE_LIVE:
        _, references = live_reference_fare_map(db)
        return references.get((route_key, advance_window_days))
    return legacy_assumption_reference_fare(route_key, advance_window_days)
