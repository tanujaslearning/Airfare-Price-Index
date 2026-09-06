"""Pipeline orchestration service executing ingestion, cleaning, and normalization."""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.quote import RawAirfareQuote, ProcessedAirfareQuote
from backend.app.services.ingestion_service import (
    COLLECTION_MODE_LIVE,
    COLLECTION_MODE_MOCK,
    run_live_ingestion,
    run_mock_ingestion,
)
from backend.app.services.cleaning_service import clean_and_normalize_raw_quotes

logger = logging.getLogger("apix.services.pipeline")


def process_raw_batch(
    db: Session,
    raw_quotes: Optional[List[RawAirfareQuote]] = None,
    job_id: Optional[int] = None,
    unprocessed_only: bool = True,
) -> Dict[str, Any]:
    """Orchestrates end-to-end cleaning and normalization for a batch of raw quotes.
    
    If raw_quotes is not passed, retrieves unprocessed raw quotes from the database.
    """
    logger.info("Starting process_raw_batch (job_id=%s)", job_id)

    if raw_quotes is None:
        query = db.query(RawAirfareQuote)
        if unprocessed_only:
            # Select raw quotes that have not yet been processed into ProcessedAirfareQuote
            already_processed_stmt = select(ProcessedAirfareQuote.raw_quote_id).where(
                ProcessedAirfareQuote.raw_quote_id.isnot(None)
            )
            query = query.filter(~RawAirfareQuote.id.in_(already_processed_stmt))

        target_raw_quotes = query.all()
    else:
        target_raw_quotes = raw_quotes

    raw_count = len(target_raw_quotes)
    if raw_count == 0:
        logger.info("No raw quotes to process in this batch")
        return {
            "status": "empty",
            "raw_quotes_count": 0,
            "processed_quotes_count": 0,
            "outliers_count": 0,
            "clean_usable_count": 0,
        }

    # Execute cleaning, deduplication, and outlier detection
    processed_quotes = clean_and_normalize_raw_quotes(db, target_raw_quotes)
    outliers_count = sum(1 for pq in processed_quotes if pq.is_outlier)
    clean_usable_count = len(processed_quotes) - outliers_count

    summary = {
        "status": "success",
        "job_id": job_id,
        "raw_quotes_count": raw_count,
        "processed_quotes_count": len(processed_quotes),
        "outliers_count": outliers_count,
        "clean_usable_count": clean_usable_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("Batch processing complete: %s", summary)
    return summary


async def run_full_mock_pipeline(
    db: Session,
    collection_date: Optional[datetime] = None,
    random_seed: int = 42,
    force_recalculate: bool = True,
) -> Dict[str, Any]:
    """Generates mock quotes, ingests them into RawAirfareQuote, executes normalization, and computes index."""
    from backend.app.services.index_engine import calculate_composite_index

    c_date = collection_date or datetime.now(timezone.utc).date()
    if isinstance(c_date, datetime):
        c_date = c_date.date()

    job, raw_quotes = await run_mock_ingestion(db, collection_date=c_date, random_seed=random_seed)
    batch_summary = process_raw_batch(db, raw_quotes=raw_quotes, job_id=job.id)

    # Calculate and persist national composite index for collection_date
    index_record = calculate_composite_index(db, target_date=c_date, collection_mode=COLLECTION_MODE_MOCK)

    return {
        "status": "success",
        "job_id": job.id,
        "source": job.source_name,
        "collection_date": c_date,
        "ingested_count": len(raw_quotes),
        "processed_quotes_count": batch_summary.get("processed_quotes_count", 0),
        "outliers_count": batch_summary.get("outliers_count", 0),
        "clean_usable_count": batch_summary.get("clean_usable_count", 0),
        "index_value": index_record.index_value if index_record else None,
        "ma_7d": index_record.ma_7d if index_record else None,
        "dod_change_pct": index_record.dod_change_pct if index_record else None,
        "collection_mode": COLLECTION_MODE_MOCK,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def run_full_live_pipeline(
    db: Session,
    collection_date: Optional[datetime] = None,
    random_seed: int = 42,
    force_recalculate: bool = True,
) -> Dict[str, Any]:
    """Runs the controlled live website pipeline without falling back to synthetic data."""
    from backend.app.services.index_engine import calculate_composite_index

    c_date = collection_date or datetime.now(timezone.utc).date()
    if isinstance(c_date, datetime):
        c_date = c_date.date()

    job, raw_quotes, live_summary = await run_live_ingestion(db, collection_date=c_date)
    if not raw_quotes:
        return {
            "status": live_summary.get("status", "failed"),
            "job_id": job.id,
            "source": job.source_name,
            "collection_date": c_date,
            "ingested_count": 0,
            "processed_quotes_count": 0,
            "outliers_count": 0,
            "clean_usable_count": 0,
            "index_value": None,
            "ma_7d": None,
            "dod_change_pct": None,
            "collection_mode": COLLECTION_MODE_LIVE,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    batch_summary = process_raw_batch(db, raw_quotes=raw_quotes, job_id=job.id)
    index_record = calculate_composite_index(db, target_date=c_date, collection_mode=COLLECTION_MODE_LIVE)

    return {
        "status": "success",
        "job_id": job.id,
        "source": job.source_name,
        "collection_date": c_date,
        "ingested_count": len(raw_quotes),
        "processed_quotes_count": batch_summary.get("processed_quotes_count", 0),
        "outliers_count": batch_summary.get("outliers_count", 0),
        "clean_usable_count": batch_summary.get("clean_usable_count", 0),
        "index_value": index_record.index_value if index_record else None,
        "ma_7d": index_record.ma_7d if index_record else None,
        "dod_change_pct": index_record.dod_change_pct if index_record else None,
        "collection_mode": COLLECTION_MODE_LIVE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def run_daily_live_pipeline_trigger(
    db: Session,
    collection_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Runs the approved daily LIVE route-window workflow for the on-demand trigger."""
    from backend.app.services.daily_collection_service import run_daily_collection

    c_date = collection_date or datetime.now(timezone.utc).date()
    if isinstance(c_date, datetime):
        c_date = c_date.date()

    result = await run_daily_collection(
        db,
        collection_date=c_date,
        calculate_index_when_sufficient=True,
    )
    job_ids = [attempt.job_id for attempt in result.attempts if attempt.job_id is not None]

    return {
        "status": result.status,
        "job_id": max(job_ids) if job_ids else 0,
        "source": "DailyLiveRouteWindowMatrix",
        "collection_date": result.collection_date,
        "ingested_count": result.total_scraped,
        "processed_quotes_count": result.total_processed,
        "outliers_count": 0,
        "clean_usable_count": result.total_processed,
        "index_value": result.index_value,
        "ma_7d": None,
        "dod_change_pct": None,
        "collection_mode": COLLECTION_MODE_LIVE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
