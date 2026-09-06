"""Quantitative calculation engine for Route Sub-Indices and National Composite Airfare Price Index (APIx)."""

import logging
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from backend.app.models.quote import ProcessedAirfareQuote, RawAirfareQuote
from backend.app.models.route import Route
from backend.app.models.index_value import AirfareIndexValue
from backend.app.data.route_basket import APPROVED_ADVANCE_WINDOWS, DEFAULT_ROUTE_BASELINES
from backend.app.services.collection_dates import collection_day_bounds_utc
from backend.app.services.dgca_route_weights import weight_by_route_code
from backend.app.services.fare_reference_service import (
    PROTOTYPE_REFERENCE_PERIOD_LABEL,
    legacy_assumption_reference_fare,
    live_reference_fare_map,
)

logger = logging.getLogger("apix.services.index_engine")

VALID_COLLECTION_MODES = {"LIVE", "MOCK"}
LIVE_INDEX_REQUIRED_COVERAGE_PCT = 100.0


def normalize_index_collection_mode(collection_mode: str) -> str:
    """Normalizes and validates index calculation provenance mode."""
    mode = (collection_mode or "").strip().upper()
    if mode not in VALID_COLLECTION_MODES:
        raise ValueError(f"Invalid collection_mode '{collection_mode}'. Expected LIVE or MOCK.")
    return mode


def get_route_baseline_fare(route_key: str, advance_window: int) -> float:
    """Returns the legacy assumed reference fare used only for MOCK/dev compatibility."""
    return legacy_assumption_reference_fare(route_key, advance_window)


def calculate_route_indices(
    db: Session,
    target_date: date,
    *,
    collection_mode: str,
) -> pd.DataFrame:
    """Calculates route-level sub-indices (R_i,w,t) across advance windows and route averages (R_i,t).
    
    Formula: R_{i,w,t} = ( Mean_Fare_{i,w,t} / Base_Fare_{i,w} ) * 100
    """
    mode = normalize_index_collection_mode(collection_mode)
    start_dt, end_dt = collection_day_bounds_utc(target_date)

    # 1. Query clean processed quotes whose raw observation was collected on target_date.
    quotes_query = (
        db.query(
            ProcessedAirfareQuote.route_id,
            ProcessedAirfareQuote.advance_window_days,
            ProcessedAirfareQuote.clean_total_fare,
            Route.origin_code,
            Route.destination_code,
        )
        .join(RawAirfareQuote, ProcessedAirfareQuote.raw_quote_id == RawAirfareQuote.id)
        .join(Route, ProcessedAirfareQuote.route_id == Route.id)
        .filter(
            ProcessedAirfareQuote.is_outlier == False,
            RawAirfareQuote.scraped_at >= start_dt,
            RawAirfareQuote.scraped_at < end_dt,
            RawAirfareQuote.collection_mode == mode,
        )
    )

    records = quotes_query.all()
    if not records:
        logger.warning(
            "No clean %s processed quotes found for collection date %s (UTC range %s to %s)",
            mode,
            target_date,
            start_dt,
            end_dt,
        )
        return pd.DataFrame()

    df = pd.DataFrame(records, columns=[
        "route_id", "advance_window_days", "clean_total_fare",
        "origin_code", "destination_code"
    ])
    df["route_key"] = df["origin_code"] + "-" + df["destination_code"]
    df["collection_mode"] = mode

    # 1. Compute Mean Fare per Route & Advance Window
    window_agg = df.groupby(["route_id", "route_key", "advance_window_days"]).agg(
        mean_fare=("clean_total_fare", "mean"),
        quote_count=("clean_total_fare", "count"),
    ).reset_index()

    # 2. Compute Sub-Index R_{i,w,t} relative to the mode-appropriate reference fare.
    if mode == "LIVE":
        reference_status, reference_fares = live_reference_fare_map(db)
        if not reference_status.is_available:
            logger.warning(
                "Cannot calculate LIVE route indices for %s: %s",
                target_date,
                reference_status.message,
            )
            return pd.DataFrame()
        window_agg["reference_fare"] = window_agg.apply(
            lambda row: reference_fares.get((row["route_key"], int(row["advance_window_days"]))),
            axis=1,
        )
        window_agg = window_agg[window_agg["reference_fare"].notna() & (window_agg["reference_fare"] > 0)].copy()
        if window_agg.empty:
            logger.warning("Cannot calculate LIVE route indices for %s: no route/window reference fares", target_date)
            return pd.DataFrame()
    else:
        window_agg["reference_fare"] = window_agg.apply(
            lambda row: get_route_baseline_fare(row["route_key"], int(row["advance_window_days"])),
            axis=1,
        )

    window_agg["sub_index"] = (window_agg["mean_fare"] / window_agg["reference_fare"]) * 100.0

    # 3. Compute Composite Route Index R_{i,t} (average across observed advance windows)
    route_agg = window_agg.groupby(["route_id", "route_key"]).agg(
        route_index=("sub_index", "mean"),
        total_quotes=("quote_count", "sum"),
        windows_observed=("advance_window_days", "count"),
    ).reset_index()
    route_agg["collection_mode"] = mode
    observed_route_ids = [int(route_id) for route_id in route_agg["route_id"].tolist()]
    observed_routes = db.query(Route).filter(Route.id.in_(observed_route_ids)).all()
    active_routes = db.query(Route).filter(Route.is_active == True).all()
    weights = weight_by_route_code(observed_routes, normalization_routes=active_routes)
    route_agg["dgca_weight"] = route_agg["route_key"].map(weights)

    route_agg["reference_period"] = PROTOTYPE_REFERENCE_PERIOD_LABEL if mode == "LIVE" else "legacy MOCK assumption"

    logger.info("Computed %s route indices for %d routes on %s", mode, len(route_agg), target_date)
    return route_agg


def calculate_composite_index(
    db: Session,
    target_date: date,
    *,
    collection_mode: str,
    frequency: str = "daily",
    baseline_period: str = "2026-Q1",
) -> Optional[AirfareIndexValue]:
    """Calculates national DGCA-weighted Composite Airfare Price Index (APIx_t) and updates rolling metrics.
    
    Formula: APIx_t = SUM( weight_i * R_{i,t} ) / SUM( weight_i )
    """
    mode = normalize_index_collection_mode(collection_mode)
    route_indices_df = calculate_route_indices(db, target_date, collection_mode=mode)
    if route_indices_df.empty:
        logger.warning("Cannot calculate %s composite index: no route index data on %s", mode, target_date)
        return None
    if mode == "LIVE":
        expected_cells, observed_cells = _live_route_window_coverage(db, target_date)
        if expected_cells == 0 or observed_cells < expected_cells:
            coverage_pct = round((observed_cells / expected_cells) * 100.0, 2) if expected_cells else 0.0
            logger.warning(
                "Cannot persist LIVE composite index for %s: insufficient LIVE route-window coverage "
                "(%d/%d, %.2f%%; required %.2f%%)",
                target_date,
                observed_cells,
                expected_cells,
                coverage_pct,
                LIVE_INDEX_REQUIRED_COVERAGE_PCT,
            )
            return None

    # 1. Weight normalization over observed routes with available official DGCA passenger traffic.
    weighted_routes_df = route_indices_df[
        route_indices_df["dgca_weight"].notna() & (route_indices_df["dgca_weight"] > 0)
    ].copy()
    if weighted_routes_df.empty:
        logger.warning(
            "Cannot calculate %s composite index: no observed routes have available DGCA traffic weights on %s",
            mode,
            target_date,
        )
        return None

    total_active_weight = weighted_routes_df["dgca_weight"].sum()
    weighted_routes_df["normalized_weight"] = weighted_routes_df["dgca_weight"] / total_active_weight

    # 2. Weighted Arithmetic Composite Index APIx_t
    composite_index_val = float(np.sum(weighted_routes_df["route_index"] * weighted_routes_df["normalized_weight"]))
    composite_index_val = round(composite_index_val, 2)

    # 3. Retrieve Historical Daily Values to compute rolling indicators
    past_records = (
        db.query(AirfareIndexValue)
        .filter(
            AirfareIndexValue.frequency == frequency,
            AirfareIndexValue.collection_mode == mode,
            AirfareIndexValue.date < target_date,
        )
        .order_by(AirfareIndexValue.date.desc())
        .limit(30)
        .all()
    )

    past_values = [p.index_value for p in past_records]

    # Calculate Day-over-Day (DoD) Percentage Change
    dod_change_pct: Optional[float] = None
    if past_values:
        prev_val = past_values[0]
        if prev_val > 0:
            dod_change_pct = round(((composite_index_val - prev_val) / prev_val) * 100.0, 2)

    # Calculate 7-Day Moving Average (including today)
    all_7d_values = [composite_index_val] + past_values[:6]
    ma_7d = round(float(np.mean(all_7d_values)), 2)

    # Calculate 30-Day Moving Average (including today)
    all_30d_values = [composite_index_val] + past_values[:29]
    ma_30d = round(float(np.mean(all_30d_values)), 2)

    # 4. Save or Update in Database
    existing_index = (
        db.query(AirfareIndexValue)
        .filter(
            AirfareIndexValue.date == target_date,
            AirfareIndexValue.frequency == frequency,
            AirfareIndexValue.collection_mode == mode,
        )
        .first()
    )

    if existing_index:
        existing_index.index_value = composite_index_val
        existing_index.collection_mode = mode
        existing_index.baseline_period = baseline_period
        existing_index.ma_7d = ma_7d
        existing_index.ma_30d = ma_30d
        existing_index.dod_change_pct = dod_change_pct
        existing_index.calculated_at = datetime.now(timezone.utc)
        record = existing_index
    else:
        record = AirfareIndexValue(
            date=target_date,
            frequency=frequency,
            collection_mode=mode,
            index_value=composite_index_val,
            baseline_period=baseline_period,
            ma_7d=ma_7d,
            ma_30d=ma_30d,
            dod_change_pct=dod_change_pct,
            calculated_at=datetime.now(timezone.utc),
        )
        db.add(record)

    db.commit()
    db.refresh(record)

    logger.info(
        "Calculated %s %s APIx for %s: index=%.2f, DoD=%.2f%%, 7d-MA=%.2f, 30d-MA=%.2f",
        mode, frequency, target_date, composite_index_val, dod_change_pct or 0.0, ma_7d, ma_30d
    )
    return record


def _live_route_window_coverage(db: Session, target_date: date) -> Tuple[int, int]:
    """Counts observed LIVE route/window cells for a collection date."""
    active_routes = db.query(Route).filter(Route.is_active == True).all()
    active_route_ids = [route.id for route in active_routes]
    expected_cells = len(active_route_ids) * len(APPROVED_ADVANCE_WINDOWS)
    if not active_route_ids:
        return 0, 0

    start_dt, end_dt = collection_day_bounds_utc(target_date)
    rows = (
        db.query(ProcessedAirfareQuote.route_id, ProcessedAirfareQuote.advance_window_days)
        .join(RawAirfareQuote, ProcessedAirfareQuote.raw_quote_id == RawAirfareQuote.id)
        .filter(
            ProcessedAirfareQuote.is_outlier == False,
            ProcessedAirfareQuote.route_id.in_(active_route_ids),
            ProcessedAirfareQuote.advance_window_days.in_(APPROVED_ADVANCE_WINDOWS),
            RawAirfareQuote.scraped_at >= start_dt,
            RawAirfareQuote.scraped_at < end_dt,
            RawAirfareQuote.collection_mode == "LIVE",
        )
        .distinct()
        .all()
    )
    observed_cells = len({(int(route_id), int(window)) for route_id, window in rows})
    return expected_cells, observed_cells


def run_pipeline_and_calculate_index(
    db: Session,
    target_date: Optional[date] = None,
    collection_mode: str = "MOCK",
) -> Dict[str, Any]:
    """Convenience pipeline function executing batch processing and subsequent index calculation."""
    from backend.app.services.pipeline_service import process_raw_batch

    t_date = target_date or datetime.now(timezone.utc).date()
    batch_res = process_raw_batch(db)
    index_record = calculate_composite_index(db, t_date, collection_mode=collection_mode)

    return {
        "batch_summary": batch_res,
        "index": {
            "date": str(index_record.date) if index_record else str(t_date),
            "collection_mode": index_record.collection_mode if index_record else collection_mode,
            "index_value": index_record.index_value if index_record else None,
            "ma_7d": index_record.ma_7d if index_record else None,
            "ma_30d": index_record.ma_30d if index_record else None,
            "dod_change_pct": index_record.dod_change_pct if index_record else None,
        } if index_record else None,
    }
