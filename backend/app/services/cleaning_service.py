"""Airfare data cleaning, tax verification, deduplication, and outlier detection pipeline."""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple
import pandas as pd
import numpy as np
from sqlalchemy.orm import Session

from backend.app.models.quote import RawAirfareQuote, ProcessedAirfareQuote

logger = logging.getLogger("apix.services.cleaning")


def verify_and_adjust_taxes(base_fare: float, taxes_fees: float, total_fare: float) -> Tuple[float, float, float]:
    """Verifies that base_fare + taxes_fees == total_fare; rectifies discrepancies."""
    clean_total = max(0.0, float(total_fare))

    # If base and taxes already sum to total within 1 paisa (0.01 INR)
    if abs((base_fare + taxes_fees) - clean_total) <= 0.01 and clean_total > 0:
        return round(base_fare, 2), round(taxes_fees, 2), round(clean_total, 2)

    # If total_fare is present and base_fare is given, derive taxes
    if clean_total > 0 and base_fare > 0 and base_fare < clean_total:
        clean_base = float(base_fare)
        clean_taxes = clean_total - clean_base
    elif clean_total > 0 and taxes_fees > 0 and taxes_fees < clean_total:
        clean_taxes = float(taxes_fees)
        clean_base = clean_total - clean_taxes
    elif clean_total > 0:
        # Standard domestic aviation breakdown approximation: ~78% base, ~22% taxes/fees
        clean_base = round(clean_total * 0.78, 2)
        clean_taxes = round(clean_total - clean_base, 2)
    else:
        clean_base = 0.0
        clean_taxes = 0.0

    return round(clean_base, 2), round(clean_taxes, 2), round(clean_total, 2)


def deduplicate_quotes_df(df: pd.DataFrame) -> pd.DataFrame:
    """Deduplicates quotes for the same flight slot, keeping the lowest available total fare.
    
    Grouping key: (route_id, source_id, flight_number, departure_datetime, advance_window_days)
    """
    if df.empty:
        return df

    dedup_cols = ["route_id", "source_id", "flight_number", "departure_datetime", "advance_window_days"]
    existing_cols = [c for c in dedup_cols if c in df.columns]

    # Sort by clean_total_fare ascending so drop_duplicates('first') picks the lowest price
    sorted_df = df.sort_values(by="clean_total_fare", ascending=True)
    deduped_df = sorted_df.drop_duplicates(subset=existing_cols, keep="first").copy()
    
    removed_count = len(df) - len(deduped_df)
    if removed_count > 0:
        logger.info("Deduplication: removed %d duplicate quotes; retained %d unique flight slots", removed_count, len(deduped_df))

    return deduped_df


def detect_outliers_df(df: pd.DataFrame, iqr_multiplier: float = 2.5) -> pd.DataFrame:
    """Flags price anomalies per (route_id, advance_window_days) using Interquartile Range (IQR).
    
    Extreme prices (e.g. glitch fares < 500 INR or extreme surge spikes > Q3 + 2.5*IQR) are flagged is_outlier=True.
    """
    if df.empty:
        df["is_outlier"] = False
        return df

    df = df.copy()
    df["is_outlier"] = False

    # Absolute sanity boundaries for Indian domestic flights
    ABSOLUTE_MIN_FARE = 500.0
    ABSOLUTE_MAX_FARE = 75000.0

    # Rule 1: Absolute sanity check
    absolute_outlier_mask = (df["clean_total_fare"] < ABSOLUTE_MIN_FARE) | (df["clean_total_fare"] > ABSOLUTE_MAX_FARE)
    df.loc[absolute_outlier_mask, "is_outlier"] = True

    if "route_id" in df.columns and "advance_window_days" in df.columns:
        for (r_id, adv), group_idx in df.groupby(["route_id", "advance_window_days"]).groups.items():
            sub = df.loc[group_idx]
            valid_fares = sub.loc[~sub["is_outlier"], "clean_total_fare"]
            if len(valid_fares) >= 4:
                q1 = np.percentile(valid_fares, 25)
                q3 = np.percentile(valid_fares, 75)
                iqr = q3 - q1
                lower_bound = max(ABSOLUTE_MIN_FARE, q1 - (iqr_multiplier * iqr))
                upper_bound = min(ABSOLUTE_MAX_FARE, q3 + (iqr_multiplier * iqr))
                
                group_outliers = (sub["clean_total_fare"] < lower_bound) | (sub["clean_total_fare"] > upper_bound)
                df.loc[sub.index[group_outliers], "is_outlier"] = True

    outlier_count = df["is_outlier"].sum()
    logger.info("Outlier detection: flagged %d quotes as outliers (out of %d)", outlier_count, len(df))
    return df


def clean_and_normalize_raw_quotes(
    db: Session,
    raw_quotes: List[RawAirfareQuote],
) -> List[ProcessedAirfareQuote]:
    """Applies the full cleaning, deduplication, and outlier detection pipeline to raw quotes,
    persisting normalized records into the processed_airfare_quotes database table.
    """
    if not raw_quotes:
        logger.info("No raw quotes provided to clean_and_normalize_raw_quotes")
        return []

    # 1. Transform raw models into Pandas DataFrame
    records = []
    for rq in raw_quotes:
        clean_base, clean_taxes, clean_total = verify_and_adjust_taxes(rq.base_fare, rq.taxes_fees, rq.total_fare)
        records.append({
            "raw_quote_id": rq.id,
            "route_id": rq.route_id,
            "source_id": rq.source_id,
            "flight_number": rq.flight_number,
            "departure_datetime": rq.departure_datetime,
            "advance_window_days": rq.advance_window_days,
            "clean_base_fare": clean_base,
            "clean_taxes_fees": clean_taxes,
            "clean_total_fare": clean_total,
            "scraped_at": rq.scraped_at,
        })

    df = pd.DataFrame(records)

    # 2. Deduplicate quotes for identical flight slots
    deduped_df = deduplicate_quotes_df(df)

    # 3. Detect and flag statistical outliers
    cleaned_df = detect_outliers_df(deduped_df)

    # 4. Instantiate and persist ProcessedAirfareQuote entities
    now_utc = datetime.now(timezone.utc)
    processed_objects: List[ProcessedAirfareQuote] = []

    for _, row in cleaned_df.iterrows():
        p_at = row["scraped_at"] if pd.notna(row["scraped_at"]) else now_utc
        proc_quote = ProcessedAirfareQuote(
            raw_quote_id=int(row["raw_quote_id"]),
            route_id=int(row["route_id"]),
            advance_window_days=int(row["advance_window_days"]),
            clean_total_fare=float(row["clean_total_fare"]),
            is_outlier=bool(row["is_outlier"]),
            processed_at=p_at,
        )
        processed_objects.append(proc_quote)

    db.add_all(processed_objects)
    db.commit()

    for obj in processed_objects:
        db.refresh(obj)

    logger.info("Successfully persisted %d processed airfare quotes", len(processed_objects))
    return processed_objects
