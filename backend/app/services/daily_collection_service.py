"""Daily controlled LIVE airfare collection workflow."""

from dataclasses import asdict, dataclass
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.data.live_source_readiness import LIVE_SOURCE_READINESS, LiveSourceReadiness
from backend.app.data.route_basket import (
    APPROVED_ADVANCE_WINDOWS,
    APPROVED_ROUTE_CODES,
    build_route_window_targets,
    validate_advance_windows,
)
from backend.app.models.airline import Airline
from backend.app.models.quote import RawAirfareQuote
from backend.app.models.route import Route
from backend.app.models.scraping_job import ScrapingJobLog
from backend.app.services.ingestion_service import (
    COLLECTION_MODE_LIVE,
    filter_duplicate_raw_quotes,
    finish_scraping_job,
    ingest_raw_quotes,
    start_scraping_job,
    validate_live_quote_contract,
)
from backend.app.services.index_engine import calculate_composite_index
from backend.app.services.live_index_service import calculate_live_only_index
from backend.app.services.pipeline_service import process_raw_batch
from scraper.airlines.air_india_scraper import AirIndiaWebsiteScraper
from scraper.airlines.akasa_scraper import AkasaWebsiteScraper
from scraper.airlines.spicejet_scraper import SpiceJetWebsiteScraper
from scraper.base.source_orchestrator import (
    ACCESS_DENIED,
    CAPTCHA,
    ERROR,
    NO_AVAILABILITY,
    RATE_LIMITED,
    ROBOTS_INCONCLUSIVE,
    SUCCESS,
    TEMPORARILY_BLOCKED,
    SourceOrchestrator,
)

logger = logging.getLogger("apix.services.daily_collection")

DAILY_STATUS_PENDING = "PENDING"
DAILY_STATUS_RUNNING = "RUNNING"
DAILY_STATUS_COMPLETED = "COMPLETED"
DAILY_STATUS_PARTIAL = "PARTIAL"
DAILY_STATUS_FAILED = "FAILED"
DAILY_STATUS_SKIPPED = "SKIPPED"

DAILY_CLASSIFICATION_SUCCESS = "VERIFIED_LIVE_DATA"
DAILY_CLASSIFICATION_SKIPPED_NOT_READY = "SKIPPED_NOT_READY"
DAILY_CLASSIFICATION_DATA_VALIDATION_FAILED = "DATA_VALIDATION_FAILED"
DAILY_CLASSIFICATION_CAPTCHA_OR_BLOCK = "CAPTCHA_OR_BLOCK"
DAILY_CLASSIFICATION_NETWORK_OR_BROWSER_FAILURE = "NETWORK_OR_BROWSER_FAILURE"
DAILY_CLASSIFICATION_NO_AVAILABILITY = "NO_AVAILABILITY"
DAILY_CLASSIFICATION_ROUTE_UNAVAILABLE = "ROUTE_UNAVAILABLE"

SOURCE_FACTORIES: Dict[str, Callable[[], Any]] = {
    "akasa": AkasaWebsiteScraper,
    "air_india": AirIndiaWebsiteScraper,
    "spicejet": SpiceJetWebsiteScraper,
}


@dataclass
class DailyCollectionAttempt:
    """Lifecycle record for one source/route/window attempt."""

    collection_date: date
    source: str
    source_key: str
    route: str
    advance_window_days: int
    departure_date: date
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str = DAILY_STATUS_PENDING
    classification: Optional[str] = None
    job_id: Optional[int] = None
    total_scraped: int = 0
    total_processed: int = 0
    error_message: Optional[str] = None


@dataclass
class DailyCollectionResult:
    """Summary of a daily controlled LIVE collection run."""

    collection_date: date
    status: str
    attempts: List[DailyCollectionAttempt]
    total_scraped: int
    total_processed: int
    index_calculated: bool
    index_value: Optional[float]
    coverage_status: Optional[str]
    message: str

    def model_dump(self) -> Dict[str, Any]:
        """Pydantic-style dump helper for scripts/tests."""
        return {
            **asdict(self),
            "collection_date": self.collection_date.isoformat(),
            "attempts": [
                {
                    **asdict(attempt),
                    "collection_date": attempt.collection_date.isoformat(),
                    "departure_date": attempt.departure_date.isoformat(),
                    "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
                    "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None,
                }
                for attempt in self.attempts
            ],
        }


def calculate_departure_date(collection_date: date, advance_window_days: int) -> date:
    """Calculates the target flight date from explicit collection context."""
    if advance_window_days not in APPROVED_ADVANCE_WINDOWS:
        raise ValueError(f"Unsupported advance_window_days {advance_window_days}; expected {APPROVED_ADVANCE_WINDOWS}.")
    return collection_date + timedelta(days=advance_window_days)


def build_daily_route_window_matrix(
    collection_date: date,
    *,
    route_codes: Optional[Sequence[str]] = None,
    advance_windows: Optional[Sequence[int]] = None,
):
    """Builds the approved daily route-window collection plan."""
    return build_route_window_targets(
        collection_date,
        route_codes=route_codes,
        advance_windows=advance_windows,
    )


def enabled_source_keys(configured: Optional[str] = None) -> List[str]:
    """Parses enabled source keys from settings or a provided comma-separated string."""
    raw_value = settings.DAILY_COLLECTION_ENABLED_SOURCES if configured is None else configured
    keys = [part.strip().lower() for part in raw_value.split(",") if part.strip()]
    return keys or ["akasa"]


def planned_source_readiness(source_keys: Optional[Sequence[str]] = None) -> List[LiveSourceReadiness]:
    """Returns source readiness records in the requested or configured order."""
    keys = list(source_keys) if source_keys is not None else enabled_source_keys()
    records: List[LiveSourceReadiness] = []
    for key in keys:
        record = LIVE_SOURCE_READINESS.get(key)
        if record is None:
            logger.warning("Ignoring unknown daily collection source key: %s", key)
            continue
        records.append(record)
    return records


async def run_daily_collection(
    db: Session,
    collection_date: Optional[date] = None,
    *,
    source_keys: Optional[Sequence[str]] = None,
    route_codes: Optional[Sequence[str]] = None,
    advance_windows: Optional[Sequence[int]] = None,
    calculate_index_when_sufficient: bool = True,
) -> DailyCollectionResult:
    """Runs controlled daily LIVE collection over configured source/route/window cells."""
    c_date = collection_date or datetime.now(ZoneInfo(settings.DAILY_COLLECTION_TIMEZONE)).date()
    windows = validate_advance_windows(advance_windows or APPROVED_ADVANCE_WINDOWS)
    routes = _active_routes(db, route_codes)
    source_readiness = planned_source_readiness(source_keys)
    source_ids = _source_ids_by_code(db)

    attempts: List[DailyCollectionAttempt] = []
    for route in routes:
        for window in windows:
            departure_date = calculate_departure_date(c_date, window)
            for source_record in source_readiness:
                attempt = DailyCollectionAttempt(
                    collection_date=c_date,
                    source=source_record.display_name,
                    source_key=source_record.key,
                    route=route.route_key,
                    advance_window_days=window,
                    departure_date=departure_date,
                )
                attempts.append(attempt)

                if source_record.status != "READY" or not source_record.enabled_by_default:
                    attempt.status = DAILY_STATUS_SKIPPED
                    attempt.classification = DAILY_CLASSIFICATION_SKIPPED_NOT_READY
                    attempt.error_message = source_record.reason
                    continue

                factory = SOURCE_FACTORIES.get(source_record.key)
                if factory is None:
                    attempt.status = DAILY_STATUS_SKIPPED
                    attempt.classification = DAILY_CLASSIFICATION_SKIPPED_NOT_READY
                    attempt.error_message = f"No scraper factory configured for {source_record.key}."
                    continue

                await _run_single_attempt(
                    db,
                    attempt=attempt,
                    route=route,
                    source_record=source_record,
                    source_id=source_ids.get(source_record.source_code or ""),
                    scraper_factory=factory,
                )
                if attempt.classification == DAILY_CLASSIFICATION_SUCCESS:
                    break

    total_scraped = sum(attempt.total_scraped for attempt in attempts)
    total_processed = sum(attempt.total_processed for attempt in attempts)
    coverage_status = None
    index_record = None
    if calculate_index_when_sufficient and total_processed > 0:
        coverage = calculate_live_only_index(db, collection_date=c_date)
        coverage_status = coverage.status
        if coverage.coverage.is_sufficient:
            index_record = calculate_composite_index(db, c_date, collection_mode=COLLECTION_MODE_LIVE)

    result_status = _daily_result_status(attempts)
    return DailyCollectionResult(
        collection_date=c_date,
        status=result_status,
        attempts=attempts,
        total_scraped=total_scraped,
        total_processed=total_processed,
        index_calculated=index_record is not None,
        index_value=index_record.index_value if index_record else None,
        coverage_status=coverage_status,
        message=f"Daily LIVE collection finished with status {result_status}.",
    )


async def _run_single_attempt(
    db: Session,
    *,
    attempt: DailyCollectionAttempt,
    route: Route,
    source_record: LiveSourceReadiness,
    source_id: Optional[int],
    scraper_factory: Callable[[], Any],
) -> None:
    attempt.status = DAILY_STATUS_RUNNING
    attempt.started_at = datetime.now(timezone.utc)
    job = start_scraping_job(
        db,
        source_name=f"DailyLive:{source_record.display_name}:{route.route_key}:T+{attempt.advance_window_days}",
    )
    attempt.job_id = job.id

    try:
        orchestrator = SourceOrchestrator(
            sources=[scraper_factory()],
            source_id_by_name={source_record.display_name: source_id},
        )
        collection_result = await orchestrator.collect_quotes(
            origin=route.origin_code,
            destination=route.destination_code,
            departure_date=attempt.departure_date,
            cabin_class="ECONOMY",
            route_id=route.id,
            source_id=source_id,
            advance_window_days=attempt.advance_window_days,
        )
        first_state = collection_result.attempts[0].state if collection_result.attempts else ERROR
        first_message = collection_result.attempts[0].message if collection_result.attempts else "No source attempt recorded."

        if first_state == NO_AVAILABILITY:
            classification = _no_availability_classification(first_message)
            _finish_attempt(db, attempt, job, DAILY_STATUS_COMPLETED, classification, 0, 0, first_message)
            return
        if first_state in {CAPTCHA, RATE_LIMITED, ACCESS_DENIED, ROBOTS_INCONCLUSIVE, TEMPORARILY_BLOCKED}:
            _finish_attempt(db, attempt, job, DAILY_STATUS_FAILED, DAILY_CLASSIFICATION_CAPTCHA_OR_BLOCK, 0, 0, first_message)
            return
        if first_state != SUCCESS:
            _finish_attempt(
                db,
                attempt,
                job,
                DAILY_STATUS_FAILED,
                DAILY_CLASSIFICATION_NETWORK_OR_BROWSER_FAILURE,
                0,
                0,
                first_message,
            )
            return
        if not collection_result.quotes:
            _finish_attempt(
                db,
                attempt,
                job,
                DAILY_STATUS_COMPLETED,
                DAILY_CLASSIFICATION_NO_AVAILABILITY,
                0,
                0,
                "Source returned success without visible fare observations.",
            )
            return

        valid_quotes, validation_errors = validate_live_quote_contract(
            collection_result.quotes,
            route=route,
            departure_date=attempt.departure_date,
            advance_window_days=attempt.advance_window_days,
        )
        if validation_errors:
            _finish_attempt(
                db,
                attempt,
                job,
                DAILY_STATUS_FAILED,
                DAILY_CLASSIFICATION_DATA_VALIDATION_FAILED,
                0,
                0,
                "; ".join(validation_errors),
            )
            return

        filtered_quotes, duplicate_count = filter_duplicate_raw_quotes(
            db,
            valid_quotes,
            collection_mode=COLLECTION_MODE_LIVE,
        )
        saved_raw = ingest_raw_quotes(db, filtered_quotes, job=job, collection_mode=COLLECTION_MODE_LIVE)
        batch_summary = process_raw_batch(db, raw_quotes=saved_raw, job_id=job.id) if saved_raw else {
            "processed_quotes_count": 0,
            "clean_usable_count": 0,
        }
        message = f"duplicates_skipped={duplicate_count}"
        _finish_attempt(
            db,
            attempt,
            job,
            DAILY_STATUS_COMPLETED,
            DAILY_CLASSIFICATION_SUCCESS,
            len(saved_raw),
            int(batch_summary.get("processed_quotes_count", 0)),
            message,
        )
    except Exception as exc:
        logger.exception("Daily collection attempt failed: %s", attempt)
        _finish_attempt(
            db,
            attempt,
            job,
            DAILY_STATUS_FAILED,
            DAILY_CLASSIFICATION_NETWORK_OR_BROWSER_FAILURE,
            0,
            0,
            str(exc),
        )


def _finish_attempt(
    db: Session,
    attempt: DailyCollectionAttempt,
    job: ScrapingJobLog,
    status: str,
    classification: str,
    total_scraped: int,
    total_processed: int,
    error_message: Optional[str],
) -> None:
    attempt.completed_at = datetime.now(timezone.utc)
    attempt.status = status
    attempt.classification = classification
    attempt.total_scraped = total_scraped
    attempt.total_processed = total_processed
    attempt.error_message = error_message
    job_status = DAILY_STATUS_COMPLETED if status == DAILY_STATUS_COMPLETED else DAILY_STATUS_FAILED
    finish_scraping_job(
        db,
        job,
        total_scraped=total_scraped,
        status=job_status,
        error_log=_job_error_log(attempt),
    )


def _job_error_log(attempt: DailyCollectionAttempt) -> Optional[str]:
    if attempt.classification == DAILY_CLASSIFICATION_SUCCESS and not attempt.error_message:
        return None
    return (
        f"collection_date={attempt.collection_date}; route={attempt.route}; "
        f"advance_window_days={attempt.advance_window_days}; departure_date={attempt.departure_date}; "
        f"classification={attempt.classification}; processed={attempt.total_processed}; "
        f"message={attempt.error_message or ''}"
    )


def _daily_result_status(attempts: Sequence[DailyCollectionAttempt]) -> str:
    if not attempts:
        return DAILY_STATUS_SKIPPED

    cell_states: List[str] = []
    for _, cell_attempts in _attempts_by_cell(attempts).items():
        active_cell_attempts = [attempt for attempt in cell_attempts if attempt.status != DAILY_STATUS_SKIPPED]
        if not active_cell_attempts:
            cell_states.append(DAILY_STATUS_SKIPPED)
        elif any(attempt.status == DAILY_STATUS_COMPLETED for attempt in active_cell_attempts):
            cell_states.append(DAILY_STATUS_COMPLETED)
        else:
            cell_states.append(DAILY_STATUS_FAILED)

    active_cells = [state for state in cell_states if state != DAILY_STATUS_SKIPPED]
    if not active_cells:
        return DAILY_STATUS_SKIPPED
    if all(state == DAILY_STATUS_COMPLETED for state in active_cells):
        return DAILY_STATUS_COMPLETED
    if any(state == DAILY_STATUS_COMPLETED for state in active_cells):
        return DAILY_STATUS_PARTIAL
    return DAILY_STATUS_FAILED


def _attempts_by_cell(attempts: Sequence[DailyCollectionAttempt]) -> Dict[Tuple[str, int], List[DailyCollectionAttempt]]:
    cells: Dict[Tuple[str, int], List[DailyCollectionAttempt]] = {}
    for attempt in attempts:
        cells.setdefault((attempt.route, attempt.advance_window_days), []).append(attempt)
    return cells


def _no_availability_classification(message: Optional[str]) -> str:
    text = (message or "").lower()
    route_unavailable_markers = (
        "airport option",
        "route unavailable",
        "route unsupported",
        "unsupported route",
        "not configured or active",
    )
    if any(marker in text for marker in route_unavailable_markers):
        return DAILY_CLASSIFICATION_ROUTE_UNAVAILABLE
    return DAILY_CLASSIFICATION_NO_AVAILABILITY


def _active_routes(db: Session, route_codes: Optional[Sequence[str]]) -> List[Route]:
    query = db.query(Route).filter(Route.is_active == True)
    routes = query.order_by(Route.id.asc()).all()
    requested = list(APPROVED_ROUTE_CODES if route_codes is None else route_codes)
    target_codes = [target.route_code for target in build_route_window_targets(date.today(), route_codes=requested, advance_windows=[1])]
    route_by_key = {route.route_key: route for route in routes}
    selected = [route_by_key[code] for code in target_codes if code in route_by_key]
    missing = set(target_codes) - set(route_by_key)
    if missing:
        raise ValueError(f"Unknown or inactive route(s): {', '.join(sorted(missing))}")
    return selected


def _source_ids_by_code(db: Session) -> Dict[str, int]:
    return {
        airline.code: airline.id
        for airline in db.query(Airline).all()
        if airline.code
    }


def attempt_counts_by_mode(db: Session) -> Dict[str, int]:
    """Returns current raw quote counts by collection mode for diagnostics."""
    rows = db.query(RawAirfareQuote.collection_mode, RawAirfareQuote.id).all()
    counts: Dict[str, int] = {}
    for mode, _ in rows:
        counts[mode] = counts.get(mode, 0) + 1
    return counts
