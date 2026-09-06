"""Data ingestion service for airfare quotes and scraper job execution logging."""

import logging
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional, Union, Dict, Any, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.data.route_basket import APPROVED_ADVANCE_WINDOWS, resolve_approved_route_code
from backend.app.models.quote import RawAirfareQuote
from backend.app.models.scraping_job import ScrapingJobLog
from backend.app.models.route import Route
from backend.app.models.airline import Airline
from backend.app.schemas.quote import RawAirfareQuoteCreate
from scraper.airlines.akasa_scraper import AkasaWebsiteScraper
from scraper.airlines.air_india_scraper import AirIndiaWebsiteScraper
from scraper.base.source_orchestrator import SourceOrchestrator
from scraper.base.mock_scraper import MockFlightScraper

logger = logging.getLogger("apix.services.ingestion")

COLLECTION_MODE_MOCK = "MOCK"
COLLECTION_MODE_LIVE = "LIVE"
VALID_COLLECTION_MODES = {COLLECTION_MODE_MOCK, COLLECTION_MODE_LIVE}
CONTROLLED_LIVE_ADVANCE_WINDOWS = set(APPROVED_ADVANCE_WINDOWS)


def start_scraping_job(db: Session, source_name: str) -> ScrapingJobLog:
    """Creates and persists an initial ScrapingJobLog audit entry."""
    job = ScrapingJobLog(
        source_name=source_name,
        status="RUNNING",
        total_scraped=0,
        start_time=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info("Started ScrapingJobLog #%d for source: %s", job.id, source_name)
    return job


def finish_scraping_job(
    db: Session,
    job: ScrapingJobLog,
    total_scraped: int,
    status: str = "COMPLETED",
    error_log: Optional[str] = None,
) -> ScrapingJobLog:
    """Updates ScrapingJobLog with final count, completion status, and timing."""
    job.total_scraped = total_scraped
    job.status = status
    job.end_time = datetime.now(timezone.utc)
    job.error_log = error_log
    db.commit()
    db.refresh(job)
    logger.info("Finished ScrapingJobLog #%d: status=%s, total=%d", job.id, status, total_scraped)
    return job


def normalize_collection_mode(collection_mode: Optional[str]) -> str:
    """Normalizes and validates raw quote provenance mode."""
    mode = (collection_mode or COLLECTION_MODE_MOCK).strip().upper()
    if mode not in VALID_COLLECTION_MODES:
        raise ValueError(f"Invalid collection_mode '{collection_mode}'. Expected MOCK or LIVE.")
    return mode


def infer_collection_mode(job: Optional[ScrapingJobLog]) -> str:
    """Infers provenance mode from the pipeline job source."""
    if job and job.source_name == "LiveWebsiteOrchestrator":
        return COLLECTION_MODE_LIVE
    return COLLECTION_MODE_MOCK


def ingest_raw_quotes(
    db: Session,
    quotes: List[Union[RawAirfareQuoteCreate, Dict[str, Any]]],
    job: Optional[ScrapingJobLog] = None,
    collection_mode: Optional[str] = None,
) -> List[RawAirfareQuote]:
    """Batch-saves raw scraped airfare quotes into the raw_airfare_quotes database table."""
    if not quotes:
        logger.warning("ingest_raw_quotes received empty quote list")
        return []

    raw_objects: List[RawAirfareQuote] = []
    now_utc = datetime.now(timezone.utc)

    for q in quotes:
        if isinstance(q, RawAirfareQuoteCreate):
            data = q.model_dump()
        elif isinstance(q, dict):
            data = q.copy()
        else:
            raise ValueError(f"Unsupported quote format: {type(q)}")

        if "scraped_at" not in data or data["scraped_at"] is None:
            data["scraped_at"] = now_utc
        if not data.get("collection_mode"):
            data["collection_mode"] = collection_mode or infer_collection_mode(job)
        data["collection_mode"] = normalize_collection_mode(data["collection_mode"])
        if data.get("scraping_job_id") is None and job is not None:
            data["scraping_job_id"] = job.id

        raw_obj = RawAirfareQuote(**data)
        raw_objects.append(raw_obj)

    db.add_all(raw_objects)
    db.commit()

    for obj in raw_objects:
        db.refresh(obj)

    logger.info("Successfully ingested %d raw airfare quotes into database", len(raw_objects))

    if job:
        job.total_scraped += len(raw_objects)
        db.commit()

    return raw_objects


def filter_duplicate_raw_quotes(
    db: Session,
    quotes: List[RawAirfareQuoteCreate],
    collection_mode: str,
) -> Tuple[List[RawAirfareQuoteCreate], int]:
    """Removes exact same-day quote duplicates before persistence."""
    mode = normalize_collection_mode(collection_mode)
    filtered: List[RawAirfareQuoteCreate] = []
    seen = set()
    duplicate_count = 0

    for quote in quotes:
        if quote.scraped_at is None:
            filtered.append(quote)
            continue

        start = datetime.combine(quote.scraped_at.date(), datetime.min.time(), tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        key = (
            quote.route_id,
            quote.source_id,
            quote.flight_number,
            quote.departure_datetime,
            quote.advance_window_days,
            mode,
            quote.scraped_at.date(),
        )
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)

        exists = (
            db.query(RawAirfareQuote.id)
            .filter(
                RawAirfareQuote.route_id == quote.route_id,
                RawAirfareQuote.source_id == quote.source_id,
                RawAirfareQuote.flight_number == quote.flight_number,
                RawAirfareQuote.departure_datetime == quote.departure_datetime,
                RawAirfareQuote.advance_window_days == quote.advance_window_days,
                RawAirfareQuote.collection_mode == mode,
                RawAirfareQuote.scraped_at >= start,
                RawAirfareQuote.scraped_at < end,
            )
            .first()
        )
        if exists:
            duplicate_count += 1
            continue
        filtered.append(quote)

    return filtered, duplicate_count


def validate_live_quote_contract(
    quotes: List[RawAirfareQuoteCreate],
    *,
    route: Route,
    departure_date: date,
    advance_window_days: int,
) -> Tuple[List[RawAirfareQuoteCreate], List[str]]:
    """Accepts only live quotes matching the requested route/date/window."""
    valid: List[RawAirfareQuoteCreate] = []
    errors: List[str] = []

    for quote in quotes:
        quote_errors = []
        if quote.route_id != route.id:
            quote_errors.append(f"route_id {quote.route_id} != {route.id}")
        if quote.departure_datetime.date() != departure_date:
            quote_errors.append(f"departure_date {quote.departure_datetime.date()} != {departure_date}")
        if quote.advance_window_days != advance_window_days:
            quote_errors.append(f"advance_window_days {quote.advance_window_days} != {advance_window_days}")
        if quote.total_fare <= 0:
            quote_errors.append(f"total_fare {quote.total_fare} <= 0")

        if quote_errors:
            flight = quote.flight_number or "UNKNOWN"
            errors.append(f"{flight}: {', '.join(quote_errors)}")
            continue
        valid.append(quote)

    return valid, errors


def get_quote_provenance_report(db: Session) -> List[Dict[str, Any]]:
    """Returns raw quote provenance counts as mode/source/job_id/quote_count rows."""
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
        normalized_mode = normalize_collection_mode(mode)
        if normalized_mode == COLLECTION_MODE_MOCK:
            source = job_source_name or "MockSyntheticEngine"
        else:
            source = airline_name or job_source_name or "UNKNOWN"
        key = (normalized_mode, source, job_id)
        totals[key] = totals.get(key, 0) + int(quote_count)

    return [
        {
            "mode": mode,
            "source": source,
            "job_id": job_id,
            "quote_count": quote_count,
        }
        for (mode, source, job_id), quote_count in sorted(totals.items())
    ]


async def run_mock_ingestion(
    db: Session,
    collection_date: Optional[date] = None,
    random_seed: int = 42,
) -> Tuple[ScrapingJobLog, List[RawAirfareQuote]]:
    """Generates synthetic quotes across all active seed routes and ingests them into DB."""
    c_date = collection_date or datetime.now(timezone.utc).date()
    job = start_scraping_job(db, source_name="MockSyntheticEngine")

    try:
        # Load active routes from database
        routes = db.query(Route).filter(Route.is_active == True).all()
        if not routes:
            raise ValueError("No active routes found in database. Run database seed first.")

        route_dicts = [
            {"id": r.id, "origin_code": r.origin_code, "destination_code": r.destination_code}
            for r in routes
        ]

        # Load airlines map
        airlines = db.query(Airline).all()
        carrier_map = {a.code: a.id for a in airlines}

        # Generate quotes matrix via mock scraper
        scraper = MockFlightScraper(random_seed=random_seed)
        quotes_create = await scraper.generate_complete_matrix(
            collection_date=c_date,
            routes=route_dicts,
            carrier_id_map=carrier_map,
        )

        # Ingest to database
        saved_raw = ingest_raw_quotes(db, quotes_create, job=job, collection_mode=COLLECTION_MODE_MOCK)
        finish_scraping_job(db, job, total_scraped=len(saved_raw), status="COMPLETED")
        return job, saved_raw

    except Exception as exc:
        logger.error("Mock ingestion failed: %s", exc)
        finish_scraping_job(db, job, total_scraped=0, status="FAILED", error_log=str(exc))
        raise


async def run_live_ingestion(
    db: Session,
    collection_date: Optional[date] = None,
    advance_window_days: int = 7,
    route_code: str = "DEL-BOM",
) -> Tuple[ScrapingJobLog, List[RawAirfareQuote], Dict[str, Any]]:
    """Runs a controlled live website collection for one approved route/window cell."""
    c_date = collection_date or datetime.now(timezone.utc).date()
    if advance_window_days not in CONTROLLED_LIVE_ADVANCE_WINDOWS:
        raise ValueError(f"Unsupported controlled live advance window: {advance_window_days}")
    normalized_route_code = resolve_approved_route_code(route_code)
    origin_code, destination_code = normalized_route_code.split("-")
    job = start_scraping_job(db, source_name="LiveWebsiteOrchestrator")

    try:
        route = (
            db.query(Route)
            .filter(
                Route.origin_code == origin_code,
                Route.destination_code == destination_code,
                Route.is_active == True,
            )
            .first()
        )
        if route is None:
            raise ValueError(f"Controlled live route {normalized_route_code} is not configured or active.")

        airlines = db.query(Airline).all()
        source_id_by_code = {airline.code: airline.id for airline in airlines}
        akasa_source_id = source_id_by_code.get("QP")
        if akasa_source_id is None:
            logger.warning("Akasa Air source QP is not present in seed data; live quotes will use source_id=None")

        departure_date = c_date + timedelta(days=advance_window_days)
        orchestrator = SourceOrchestrator(
            sources=[AkasaWebsiteScraper(), AirIndiaWebsiteScraper()],
            source_id_by_name={
                "Akasa Air": akasa_source_id,
                "Air India": source_id_by_code.get("AI"),
            },
        )
        collection_result = await orchestrator.collect_quotes(
            origin=route.origin_code,
            destination=route.destination_code,
            departure_date=departure_date,
            cabin_class="ECONOMY",
            route_id=route.id,
            source_id=akasa_source_id,
            advance_window_days=advance_window_days,
        )

        if not collection_result.quotes:
            error_log = "; ".join(f"{a.source_name}: {a.state}: {a.message}" for a in collection_result.attempts)
            finish_scraping_job(db, job, total_scraped=0, status="FAILED", error_log=error_log)
            return job, [], {
                "status": "failed",
                "attempts": collection_result.attempts,
                "message": error_log,
            }

        valid_quotes, validation_errors = validate_live_quote_contract(
            collection_result.quotes,
            route=route,
            departure_date=departure_date,
            advance_window_days=advance_window_days,
        )
        if validation_errors:
            error_log = "Live quote contract validation failed: " + "; ".join(validation_errors)
            finish_scraping_job(db, job, total_scraped=0, status="FAILED", error_log=error_log)
            return job, [], {
                "status": "failed",
                "attempts": collection_result.attempts,
                "advance_window_days": advance_window_days,
                "departure_date": departure_date,
                "validation_errors": validation_errors,
                "message": error_log,
            }

        filtered_quotes, duplicate_count = filter_duplicate_raw_quotes(
            db,
            valid_quotes,
            collection_mode=COLLECTION_MODE_LIVE,
        )
        saved_raw = ingest_raw_quotes(db, filtered_quotes, job=job, collection_mode=COLLECTION_MODE_LIVE)
        finish_scraping_job(db, job, total_scraped=len(saved_raw), status="COMPLETED")
        return job, saved_raw, {
            "status": "success",
            "attempts": collection_result.attempts,
            "advance_window_days": advance_window_days,
            "departure_date": departure_date,
            "duplicates_skipped": duplicate_count,
            "message": "Live website collection completed.",
        }

    except Exception as exc:
        logger.error("Live ingestion failed: %s", exc)
        finish_scraping_job(db, job, total_scraped=0, status="FAILED", error_log=str(exc))
        raise
