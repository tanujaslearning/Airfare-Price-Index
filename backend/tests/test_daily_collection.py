"""Tests for daily controlled LIVE airfare collection workflow."""

from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base_class import Base
from backend.app.data.live_source_readiness import LiveSourceReadiness
from backend.app.data.route_basket import (
    APPROVED_ADVANCE_WINDOWS,
    APPROVED_ROUTE_BASKET,
    APPROVED_ROUTE_CODES,
    APPROVED_ROUTE_WINDOW_COUNT,
    DEFAULT_ROUTE_BASELINES,
    ROUTE_PROFILES,
)
from backend.app.db.seed import seed_database
from backend.app.models.airline import Airline
from backend.app.models.index_value import AirfareIndexValue
from backend.app.models.quote import RawAirfareQuote
from backend.app.models.route import Route
from backend.app.models.scraping_job import ScrapingJobLog
from backend.app.schemas.quote import RawAirfareQuoteCreate
from backend.app.services import daily_collection_service
from backend.app.services.daily_collection_service import (
    DAILY_CLASSIFICATION_CAPTCHA_OR_BLOCK,
    DAILY_CLASSIFICATION_NO_AVAILABILITY,
    DAILY_CLASSIFICATION_ROUTE_UNAVAILABLE,
    DAILY_CLASSIFICATION_SKIPPED_NOT_READY,
    DAILY_CLASSIFICATION_SUCCESS,
    DAILY_STATUS_COMPLETED,
    DAILY_STATUS_FAILED,
    DAILY_STATUS_PARTIAL,
    DAILY_STATUS_SKIPPED,
    build_daily_route_window_matrix,
    calculate_departure_date,
    run_daily_collection,
)
from backend.app.services.index_engine import DEFAULT_ROUTE_BASELINES as INDEX_ROUTE_BASELINES
from backend.app.services.ingestion_service import CONTROLLED_LIVE_ADVANCE_WINDOWS
from scraper.base.mock_scraper import ADVANCE_WINDOWS, ROUTE_PROFILES as MOCK_ROUTE_PROFILES
from scraper.base.base_scraper import CaptchaDetectedException, RobotsInconclusiveException, RouteUnavailableException, ScraperConfig
from scraper.scheduler.daily_scheduler import create_daily_collection_scheduler, parse_daily_collection_time


@pytest.fixture(scope="function")
def db_session():
    """In-memory SQLite session fixture."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    seed_database(db=session)
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)


class FakeDailyScraper:
    """Minimal scraper-compatible fake used by SourceOrchestrator tests."""

    def __init__(
        self,
        source_name: str = "Akasa Air",
        flight_prefix: str = "QP",
        exc: Optional[Exception] = None,
        fail_routes: Optional[set[str]] = None,
        empty_routes: Optional[set[str]] = None,
        unavailable_routes: Optional[set[str]] = None,
    ):
        self.config = ScraperConfig(source_name=source_name, base_url=f"https://{flight_prefix.lower()}.example")
        self.flight_prefix = flight_prefix
        self.exc = exc
        self.fail_routes = fail_routes or set()
        self.empty_routes = empty_routes or set()
        self.unavailable_routes = unavailable_routes or set()

    async def fetch_quotes(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str = "ECONOMY",
        route_id: int = 1,
        source_id: Optional[int] = None,
        advance_window_days: Optional[int] = None,
    ) -> List[RawAirfareQuoteCreate]:
        route_code = f"{origin}-{destination}"
        if route_code in self.unavailable_routes:
            raise RouteUnavailableException(f"{self.config.source_name} airport option {destination} was not visible")
        if route_code in self.fail_routes:
            raise TimeoutError(f"network timeout for {route_code}")
        if self.exc:
            raise self.exc
        if route_code in self.empty_routes:
            return []
        dep_dt = datetime.combine(departure_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=9)
        return [
            RawAirfareQuoteCreate(
                source_id=source_id,
                route_id=route_id,
                flight_number=f"{self.flight_prefix}-{route_code}-{advance_window_days}",
                departure_datetime=dep_dt,
                arrival_datetime=dep_dt + timedelta(hours=2),
                advance_window_days=advance_window_days or 0,
                base_fare=0.0,
                taxes_fees=0.0,
                total_fare=7200.0,
                cabin_class=cabin_class,
                scraped_at=datetime(2026, 9, 5, 6, 0, tzinfo=timezone.utc),
            )
        ]


def _raw_counts(db_session):
    return {
        "live": db_session.query(RawAirfareQuote).filter(RawAirfareQuote.collection_mode == "LIVE").count(),
        "mock": db_session.query(RawAirfareQuote).filter(RawAirfareQuote.collection_mode == "MOCK").count(),
        "jobs": db_session.query(ScrapingJobLog).count(),
        "indexes": db_session.query(AirfareIndexValue).count(),
    }


def test_calculate_departure_date_for_all_approved_windows():
    """Verify collection_date and requested windows determine departure_date."""
    collection_date = date(2026, 9, 5)

    assert calculate_departure_date(collection_date, 1) == date(2026, 9, 6)
    assert calculate_departure_date(collection_date, 7) == date(2026, 9, 12)
    assert calculate_departure_date(collection_date, 15) == date(2026, 9, 20)
    assert calculate_departure_date(collection_date, 30) == date(2026, 10, 5)
    assert calculate_departure_date(collection_date, 45) == date(2026, 10, 20)

    with pytest.raises(ValueError):
        calculate_departure_date(collection_date, 2)


def test_daily_route_window_matrix_uses_central_six_by_five_basket():
    """Verify the daily target matrix is the approved 6 routes x 5 windows."""
    collection_date = date(2026, 9, 5)

    targets = build_daily_route_window_matrix(collection_date)

    assert APPROVED_ROUTE_CODES == ("DEL-BOM", "DEL-BLR", "BOM-BLR", "DEL-CCU", "BLR-HYD", "MAA-DEL")
    assert APPROVED_ADVANCE_WINDOWS == (1, 7, 15, 30, 45)
    assert len(targets) == APPROVED_ROUTE_WINDOW_COUNT == 30
    assert len({(target.route_code, target.advance_window_days) for target in targets}) == 30
    assert {(target.route_code, target.advance_window_days) for target in targets} == {
        (route_code, window)
        for route_code in APPROVED_ROUTE_CODES
        for window in APPROVED_ADVANCE_WINDOWS
    }
    assert set(target.route_code for target in targets) == set(APPROVED_ROUTE_CODES)
    assert set(target.advance_window_days for target in targets) == set(APPROVED_ADVANCE_WINDOWS)
    for route_code in APPROVED_ROUTE_CODES:
        assert [target.advance_window_days for target in targets if target.route_code == route_code] == [1, 7, 15, 30, 45]
    assert {target.departure_date for target in targets if target.advance_window_days == 1} == {date(2026, 9, 6)}
    assert {target.departure_date for target in targets if target.advance_window_days == 45} == {date(2026, 10, 20)}


def test_all_six_approved_routes_are_seeded(db_session):
    """Verify route-independent daily defaults target the full active approved basket."""
    routes = db_session.query(Route).filter(Route.is_active == True).order_by(Route.id.asc()).all()

    assert [route.route_key for route in routes] == list(APPROVED_ROUTE_CODES)


def test_route_and_window_definitions_are_not_duplicated_in_runtime_config():
    """Verify seed/mock/index/live constants point at the central approved basket."""
    assert [route.route_code for route in APPROVED_ROUTE_BASKET] == list(APPROVED_ROUTE_CODES)
    assert ADVANCE_WINDOWS == list(APPROVED_ADVANCE_WINDOWS)
    assert CONTROLLED_LIVE_ADVANCE_WINDOWS == set(APPROVED_ADVANCE_WINDOWS)
    assert MOCK_ROUTE_PROFILES == ROUTE_PROFILES
    assert INDEX_ROUTE_BASELINES == DEFAULT_ROUTE_BASELINES


def test_daily_scheduler_configuration():
    """Verify scheduler time parsing and daily job registration."""
    assert parse_daily_collection_time("06:00") == (6, 0)
    assert parse_daily_collection_time("23:59") == (23, 59)
    with pytest.raises(ValueError):
        parse_daily_collection_time("25:00")

    scheduler = create_daily_collection_scheduler(collection_time="06:00", timezone_name="Asia/Kolkata")
    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].id == "daily_live_airfare_collection"
    assert str(scheduler.timezone) == "Asia/Kolkata"


@pytest.mark.asyncio
async def test_daily_collection_single_cell_preserves_live_provenance(monkeypatch, db_session):
    """Verify one source/route/window inserts validated LIVE raw and processed quotes."""
    before = _raw_counts(db_session)
    monkeypatch.setitem(daily_collection_service.SOURCE_FACTORIES, "akasa", lambda: FakeDailyScraper())

    result = await run_daily_collection(
        db_session,
        collection_date=date(2026, 9, 5),
        source_keys=["akasa"],
        route_codes=["DEL-BOM"],
        advance_windows=[1],
    )

    after = _raw_counts(db_session)
    attempt = result.attempts[0]
    live_quote = db_session.query(RawAirfareQuote).filter(RawAirfareQuote.collection_mode == "LIVE").one()

    assert result.status == DAILY_STATUS_COMPLETED
    assert result.index_calculated is False
    assert attempt.classification == DAILY_CLASSIFICATION_SUCCESS
    assert attempt.departure_date == date(2026, 9, 6)
    assert attempt.advance_window_days == 1
    assert attempt.job_id is not None
    assert attempt.total_scraped == 1
    assert attempt.total_processed == 1
    assert live_quote.collection_mode == "LIVE"
    assert live_quote.scraping_job_id == attempt.job_id
    assert live_quote.source_id == db_session.query(Airline).filter(Airline.code == "QP").one().id
    assert live_quote.route_id == db_session.query(Route).filter(Route.origin_code == "DEL", Route.destination_code == "BOM").one().id
    assert live_quote.departure_datetime.date() == date(2026, 9, 6)
    assert live_quote.advance_window_days == 1
    assert after["live"] == before["live"] + 1
    assert after["mock"] == before["mock"]
    assert after["indexes"] == before["indexes"]


@pytest.mark.asyncio
async def test_daily_collection_defaults_to_full_thirty_cell_matrix(monkeypatch, db_session):
    """Verify the route-independent default plan covers all approved routes/windows."""
    monkeypatch.setitem(daily_collection_service.SOURCE_FACTORIES, "akasa", lambda: FakeDailyScraper(empty_routes=set(APPROVED_ROUTE_CODES)))

    result = await run_daily_collection(
        db_session,
        collection_date=date(2026, 9, 5),
        source_keys=["akasa"],
        calculate_index_when_sufficient=False,
    )

    assert len(result.attempts) == APPROVED_ROUTE_WINDOW_COUNT
    assert {(attempt.route, attempt.advance_window_days) for attempt in result.attempts} == {
        (route_code, window)
        for route_code in APPROVED_ROUTE_CODES
        for window in APPROVED_ADVANCE_WINDOWS
    }


@pytest.mark.asyncio
async def test_daily_collection_skips_not_ready_sources(db_session):
    """Verify disabled/inconclusive sources are recorded as skipped without creating jobs."""
    before = _raw_counts(db_session)

    result = await run_daily_collection(
        db_session,
        collection_date=date(2026, 9, 5),
        source_keys=["air_india"],
        route_codes=["DEL-BOM"],
        advance_windows=[1],
    )

    after = _raw_counts(db_session)
    attempt = result.attempts[0]

    assert result.status == DAILY_STATUS_SKIPPED
    assert attempt.status == DAILY_STATUS_SKIPPED
    assert attempt.classification == DAILY_CLASSIFICATION_SKIPPED_NOT_READY
    assert attempt.job_id is None
    assert after == before


@pytest.mark.asyncio
async def test_daily_collection_no_availability_is_completed_zero_quote_outcome(monkeypatch, db_session):
    """Verify public no-availability is not treated as a browser/parser failure."""
    monkeypatch.setitem(
        daily_collection_service.SOURCE_FACTORIES,
        "akasa",
        lambda: FakeDailyScraper(exc=RouteUnavailableException("No visible fare cards")),
    )

    result = await run_daily_collection(
        db_session,
        collection_date=date(2026, 9, 5),
        source_keys=["akasa"],
        route_codes=["DEL-BOM"],
        advance_windows=[7],
    )

    attempt = result.attempts[0]
    job = db_session.query(ScrapingJobLog).filter(ScrapingJobLog.id == attempt.job_id).one()

    assert result.status == DAILY_STATUS_COMPLETED
    assert attempt.status == DAILY_STATUS_COMPLETED
    assert attempt.classification == DAILY_CLASSIFICATION_NO_AVAILABILITY
    assert attempt.total_scraped == 0
    assert attempt.total_processed == 0
    assert job.status == "COMPLETED"


@pytest.mark.asyncio
async def test_daily_collection_route_unavailable_is_recorded_without_retries(monkeypatch, db_session):
    """Verify unsupported routes get a specific classification and no quote writes."""
    before = _raw_counts(db_session)
    monkeypatch.setitem(
        daily_collection_service.SOURCE_FACTORIES,
        "akasa",
        lambda: FakeDailyScraper(unavailable_routes={"DEL-BLR"}),
    )

    result = await run_daily_collection(
        db_session,
        collection_date=date(2026, 9, 5),
        source_keys=["akasa"],
        route_codes=["DEL-BLR"],
        advance_windows=[1],
    )

    after = _raw_counts(db_session)
    attempt = result.attempts[0]

    assert result.status == DAILY_STATUS_COMPLETED
    assert attempt.classification == DAILY_CLASSIFICATION_ROUTE_UNAVAILABLE
    assert attempt.total_scraped == 0
    assert after["live"] == before["live"]
    assert after["mock"] == before["mock"]


@pytest.mark.asyncio
async def test_daily_collection_captcha_block_is_failed_attempt(monkeypatch, db_session):
    """Verify CAPTCHA/block stops only that attempt and records the classification."""
    monkeypatch.setitem(
        daily_collection_service.SOURCE_FACTORIES,
        "akasa",
        lambda: FakeDailyScraper(exc=CaptchaDetectedException("captcha")),
    )

    result = await run_daily_collection(
        db_session,
        collection_date=date(2026, 9, 5),
        source_keys=["akasa"],
        route_codes=["DEL-BOM"],
        advance_windows=[1],
    )

    attempt = result.attempts[0]
    assert result.status == DAILY_STATUS_FAILED
    assert attempt.status == DAILY_STATUS_FAILED
    assert attempt.classification == DAILY_CLASSIFICATION_CAPTCHA_OR_BLOCK
    assert attempt.total_scraped == 0


@pytest.mark.asyncio
async def test_daily_collection_robots_inconclusive_skips_live_without_mock_fallback(monkeypatch, db_session):
    """Verify robots uncertainty fails the LIVE attempt and never inserts MOCK fallback data."""
    before = _raw_counts(db_session)
    monkeypatch.setitem(
        daily_collection_service.SOURCE_FACTORIES,
        "akasa",
        lambda: FakeDailyScraper(exc=RobotsInconclusiveException("robots timeout")),
    )

    result = await run_daily_collection(
        db_session,
        collection_date=date(2026, 9, 5),
        source_keys=["akasa"],
        route_codes=["DEL-BOM"],
        advance_windows=[1],
    )

    after = _raw_counts(db_session)
    attempt = result.attempts[0]

    assert result.status == DAILY_STATUS_FAILED
    assert attempt.status == DAILY_STATUS_FAILED
    assert attempt.classification == DAILY_CLASSIFICATION_CAPTCHA_OR_BLOCK
    assert attempt.total_scraped == 0
    assert after["live"] == before["live"]
    assert after["mock"] == before["mock"]


@pytest.mark.asyncio
async def test_daily_collection_fails_over_from_blocked_source_to_next_ready_source(monkeypatch, db_session):
    """Verify a blocked source is recorded and the cell can succeed from a later source."""
    monkeypatch.setitem(
        daily_collection_service.LIVE_SOURCE_READINESS,
        "air_india",
        LiveSourceReadiness(
            key="air_india",
            display_name="Air India",
            source_code="AI",
            status="READY",
            enabled_by_default=True,
            reason="Test fallback source.",
        ),
    )
    monkeypatch.setitem(
        daily_collection_service.SOURCE_FACTORIES,
        "akasa",
        lambda: FakeDailyScraper(exc=CaptchaDetectedException("captcha")),
    )
    monkeypatch.setitem(
        daily_collection_service.SOURCE_FACTORIES,
        "air_india",
        lambda: FakeDailyScraper(source_name="Air India", flight_prefix="AI"),
    )

    result = await run_daily_collection(
        db_session,
        collection_date=date(2026, 9, 5),
        source_keys=["akasa", "air_india"],
        route_codes=["DEL-BOM"],
        advance_windows=[1],
    )

    assert result.status == DAILY_STATUS_COMPLETED
    assert len(result.attempts) == 2
    assert result.attempts[0].classification == DAILY_CLASSIFICATION_CAPTCHA_OR_BLOCK
    assert result.attempts[1].classification == DAILY_CLASSIFICATION_SUCCESS
    assert result.total_scraped == 1
    saved_quote = db_session.query(RawAirfareQuote).filter(RawAirfareQuote.collection_mode == "LIVE").one()
    assert saved_quote.airline_source.code == "AI"


@pytest.mark.asyncio
async def test_daily_collection_continues_after_partial_failure(monkeypatch, db_session):
    """Verify one failed route/window cell does not terminate the daily run."""
    monkeypatch.setitem(
        daily_collection_service.SOURCE_FACTORIES,
        "akasa",
        lambda: FakeDailyScraper(fail_routes={"DEL-BLR"}),
    )

    result = await run_daily_collection(
        db_session,
        collection_date=date(2026, 9, 5),
        source_keys=["akasa"],
        route_codes=["DEL-BOM", "DEL-BLR"],
        advance_windows=[1],
    )

    assert result.status == DAILY_STATUS_PARTIAL
    assert len(result.attempts) == 2
    assert [attempt.status for attempt in result.attempts] == [DAILY_STATUS_COMPLETED, DAILY_STATUS_FAILED]
    assert result.total_scraped == 1
    assert result.total_processed == 1
    assert db_session.query(RawAirfareQuote).filter(RawAirfareQuote.collection_mode == "MOCK").count() == 0
