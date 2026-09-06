"""Read-only provenance and live-only reporting queries."""

from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models.airline import Airline
from backend.app.models.quote import ProcessedAirfareQuote, RawAirfareQuote
from backend.app.models.route import Route
from backend.app.models.scraping_job import ScrapingJobLog
from backend.app.schemas.provenance import (
    LiveQuoteItem,
    LiveSummaryItem,
    ProvenanceJobItem,
    ProvenanceSummaryItem,
)
from backend.app.services.collection_dates import collection_date_from_timestamp, collection_day_bounds_utc
from backend.app.services.ingestion_service import COLLECTION_MODE_LIVE, COLLECTION_MODE_MOCK


def normalize_route_code(route_code: str) -> str:
    """Normalizes DEL-BOM and DELBOM style route codes."""
    clean = route_code.strip().upper()
    if "-" in clean:
        parts = clean.split("-")
        if len(parts) == 2 and all(len(part) == 3 for part in parts):
            return f"{parts[0]}-{parts[1]}"
    if len(clean) == 6:
        return f"{clean[:3]}-{clean[3:]}"
    raise ValueError("route_code must be in DEL-BOM or DELBOM format")


def resolve_route(db: Session, route_code: Optional[str]) -> Optional[Route]:
    """Returns a route for a provided route code, or None when omitted."""
    if route_code is None:
        return None
    normalized = normalize_route_code(route_code)
    origin, destination = normalized.split("-")
    return (
        db.query(Route)
        .filter(Route.origin_code == origin, Route.destination_code == destination)
        .first()
    )


def resolve_source(db: Session, source: Optional[str]) -> Optional[Airline]:
    """Returns an airline/source matching code or name, or None when omitted."""
    if source is None:
        return None
    clean = source.strip()
    if not clean:
        raise ValueError("source must not be empty")
    return (
        db.query(Airline)
        .filter((func.upper(Airline.code) == clean.upper()) | (func.upper(Airline.name) == clean.upper()))
        .first()
    )


def day_bounds(collection_date: Optional[date]) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Returns configured local collection-day bounds as UTC timestamps."""
    if collection_date is None:
        return None, None
    return collection_day_bounds_utc(collection_date)


def provenance_summary(db: Session) -> List[ProvenanceSummaryItem]:
    """Returns raw quote counts grouped by mode/source/job."""
    rows = (
        db.query(
            RawAirfareQuote.collection_mode,
            RawAirfareQuote.scraping_job_id,
            Airline.name.label("airline_name"),
            ScrapingJobLog.source_name.label("job_source_name"),
            func.count(RawAirfareQuote.id).label("quote_count"),
        )
        .outerjoin(Airline, RawAirfareQuote.source_id == Airline.id)
        .outerjoin(ScrapingJobLog, RawAirfareQuote.scraping_job_id == ScrapingJobLog.id)
        .group_by(
            RawAirfareQuote.collection_mode,
            RawAirfareQuote.scraping_job_id,
            Airline.name,
            ScrapingJobLog.source_name,
        )
        .all()
    )

    totals: Dict[Tuple[str, str, Optional[int]], int] = {}
    for mode, job_id, airline_name, job_source_name, quote_count in rows:
        if mode == COLLECTION_MODE_LIVE:
            source = airline_name or job_source_name or "UNKNOWN"
        else:
            source = job_source_name or "MockSyntheticEngine"
        key = (mode, source, job_id)
        totals[key] = totals.get(key, 0) + int(quote_count)

    return [
        ProvenanceSummaryItem(
            collection_mode=mode,
            source=source,
            job_id=job_id,
            quote_count=quote_count,
        )
        for (mode, source, job_id), quote_count in sorted(totals.items())
    ]


def live_summary(
    db: Session,
    route: Optional[Route] = None,
    source: Optional[Airline] = None,
    advance_window_days: Optional[int] = None,
    collection_date: Optional[date] = None,
) -> List[LiveSummaryItem]:
    """Returns live-only processed fare aggregates."""
    start, end = day_bounds(collection_date)
    query = (
        db.query(
            Route.origin_code,
            Route.destination_code,
            Airline.name.label("source_name"),
            ProcessedAirfareQuote.advance_window_days,
            ProcessedAirfareQuote.clean_total_fare,
            RawAirfareQuote.scraped_at,
        )
        .join(RawAirfareQuote, ProcessedAirfareQuote.raw_quote_id == RawAirfareQuote.id)
        .join(Route, RawAirfareQuote.route_id == Route.id)
        .outerjoin(Airline, RawAirfareQuote.source_id == Airline.id)
        .filter(RawAirfareQuote.collection_mode == COLLECTION_MODE_LIVE)
    )
    if route is not None:
        query = query.filter(RawAirfareQuote.route_id == route.id)
    if source is not None:
        query = query.filter(RawAirfareQuote.source_id == source.id)
    if advance_window_days is not None:
        query = query.filter(ProcessedAirfareQuote.advance_window_days == advance_window_days)
    if start is not None and end is not None:
        query = query.filter(RawAirfareQuote.scraped_at >= start, RawAirfareQuote.scraped_at < end)

    aggregates: Dict[Tuple[str, str, int, date], List[float]] = {}
    for row in query.all():
        collection_day = collection_date_from_timestamp(row.scraped_at)
        key = (
            f"{row.origin_code}-{row.destination_code}",
            row.source_name or "UNKNOWN",
            int(row.advance_window_days),
            collection_day,
        )
        aggregates.setdefault(key, []).append(float(row.clean_total_fare))

    return [
        LiveSummaryItem(
            route=route_key,
            source=source_name,
            advance_window_days=window,
            collection_date=collection_day,
            quote_count=len(fares),
            mean_fare=round(sum(fares) / len(fares), 2),
            min_fare=round(min(fares), 2),
            max_fare=round(max(fares), 2),
        )
        for (route_key, source_name, window, collection_day), fares in sorted(
            aggregates.items(),
            key=lambda item: (item[0][3], item[0][0], item[0][2]),
            reverse=True,
        )
    ]


def provenance_jobs(db: Session) -> List[ProvenanceJobItem]:
    """Returns completed/failed collection jobs with visible collection mode."""
    jobs = (
        db.query(ScrapingJobLog)
        .filter(ScrapingJobLog.status.in_(["COMPLETED", "FAILED"]))
        .order_by(ScrapingJobLog.id.desc())
        .all()
    )
    items: List[ProvenanceJobItem] = []
    for job in jobs:
        rows = (
            db.query(
                RawAirfareQuote.collection_mode,
                Airline.name.label("airline_name"),
                func.count(RawAirfareQuote.id).label("quote_count"),
                func.min(RawAirfareQuote.scraped_at).label("collection_timestamp"),
            )
            .outerjoin(Airline, RawAirfareQuote.source_id == Airline.id)
            .filter(RawAirfareQuote.scraping_job_id == job.id)
            .group_by(RawAirfareQuote.collection_mode, Airline.name)
            .all()
        )
        if rows:
            grouped_rows: Dict[Tuple[str, str, Optional[str]], int] = {}
            for row in rows:
                mode = row.collection_mode or _infer_mode_from_job(job)
                source_name = row.airline_name if mode == COLLECTION_MODE_LIVE else job.source_name
                collection_day = collection_date_from_timestamp(row.collection_timestamp) if row.collection_timestamp else None
                key = (mode, source_name or job.source_name, str(collection_day) if collection_day else None)
                grouped_rows[key] = grouped_rows.get(key, 0) + int(row.quote_count)
            for (mode, source_name, collection_date), quote_count in grouped_rows.items():
                items.append(
                    ProvenanceJobItem(
                        job_id=job.id,
                        source=source_name,
                        collection_mode=mode,
                        status=job.status,
                        collection_date=date.fromisoformat(collection_date) if collection_date else None,
                        quote_count=quote_count,
                        started_at=job.start_time,
                        completed_at=job.end_time,
                    )
                )
        else:
            items.append(
                ProvenanceJobItem(
                    job_id=job.id,
                    source=job.source_name,
                    collection_mode=_infer_mode_from_job(job),
                    status=job.status,
                    collection_date=collection_date_from_timestamp(job.start_time) if job.start_time else None,
                    quote_count=job.total_scraped,
                    started_at=job.start_time,
                    completed_at=job.end_time,
                )
            )
    return items


def live_quotes(
    db: Session,
    route: Optional[Route] = None,
    source: Optional[Airline] = None,
    advance_window_days: Optional[int] = None,
    collection_date: Optional[date] = None,
    limit: int = 100,
    offset: int = 0,
) -> Tuple[int, List[LiveQuoteItem]]:
    """Returns paginated live-only raw quotes."""
    start, end = day_bounds(collection_date)
    query = (
        db.query(RawAirfareQuote)
        .join(Route, RawAirfareQuote.route_id == Route.id)
        .outerjoin(Airline, RawAirfareQuote.source_id == Airline.id)
        .filter(RawAirfareQuote.collection_mode == COLLECTION_MODE_LIVE)
    )
    if route is not None:
        query = query.filter(RawAirfareQuote.route_id == route.id)
    if source is not None:
        query = query.filter(RawAirfareQuote.source_id == source.id)
    if advance_window_days is not None:
        query = query.filter(RawAirfareQuote.advance_window_days == advance_window_days)
    if start is not None and end is not None:
        query = query.filter(RawAirfareQuote.scraped_at >= start, RawAirfareQuote.scraped_at < end)

    total = query.count()
    quotes = (
        query.order_by(RawAirfareQuote.scraped_at.desc(), RawAirfareQuote.id.asc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    items = [
        LiveQuoteItem(
            quote_id=quote.id,
            route=quote.route.route_key,
            source=quote.airline_source.name if quote.airline_source else "UNKNOWN",
            flight_number=quote.flight_number,
            departure_datetime=quote.departure_datetime,
            arrival_datetime=quote.arrival_datetime,
            advance_window_days=quote.advance_window_days,
            base_fare=quote.base_fare,
            taxes_fees=quote.taxes_fees,
            total_fare=quote.total_fare,
            cabin_class=quote.cabin_class,
            scraped_at=quote.scraped_at,
            scraping_job_id=quote.scraping_job_id,
        )
        for quote in quotes
    ]
    return total, items


def _infer_mode_from_job(job: ScrapingJobLog) -> str:
    source_name = job.source_name or ""
    if source_name == "LiveWebsiteOrchestrator" or source_name.startswith("DailyLive:"):
        return COLLECTION_MODE_LIVE
    return COLLECTION_MODE_MOCK
