"""Unit tests for data ingestion, tax verification, deduplication, outlier detection, and normalization."""

import pytest
import pandas as pd
from datetime import datetime, date, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base_class import Base
from backend.app.models.route import Route
from backend.app.models.airline import Airline
from backend.app.models.quote import RawAirfareQuote, ProcessedAirfareQuote
from backend.app.models.scraping_job import ScrapingJobLog
from backend.app.db.seed import seed_database

from backend.app.services.cleaning_service import (
    verify_and_adjust_taxes,
    deduplicate_quotes_df,
    detect_outliers_df,
    clean_and_normalize_raw_quotes,
)
from backend.app.services.ingestion_service import (
    start_scraping_job,
    finish_scraping_job,
    filter_duplicate_raw_quotes,
    get_quote_provenance_report,
    ingest_raw_quotes,
    run_mock_ingestion,
)
from backend.app.services import ingestion_service
from backend.app.services.pipeline_service import (
    process_raw_batch,
    run_full_mock_pipeline,
)
from backend.app.schemas.quote import RawAirfareQuoteCreate
from scraper.base.source_orchestrator import SourceAttempt, SourceCollectionResult, SUCCESS


@pytest.fixture(scope="function")
def db_session():
    """In-memory SQLite session fixture."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_verify_and_adjust_taxes():
    """Verify base fare + taxes/fees consistency enforcement."""
    # Case 1: Exact match
    b, t, tot = verify_and_adjust_taxes(base_fare=3500.0, taxes_fees=1000.0, total_fare=4500.0)
    assert b == 3500.0
    assert t == 1000.0
    assert tot == 4500.0

    # Case 2: Missing taxes (total = 5000, base = 4000, taxes = 0)
    b, t, tot = verify_and_adjust_taxes(base_fare=4000.0, taxes_fees=0.0, total_fare=5000.0)
    assert b == 4000.0
    assert t == 1000.0
    assert tot == 5000.0

    # Case 3: Missing base fare (total = 6000, base = 0, taxes = 1200)
    b, t, tot = verify_and_adjust_taxes(base_fare=0.0, taxes_fees=1200.0, total_fare=6000.0)
    assert b == 4800.0
    assert t == 1200.0
    assert tot == 6000.0


def test_deduplication_keeps_lowest_fare():
    """Verify deduplication keeps the cheapest available fare for a given flight slot."""
    dep_time = datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)
    
    # 3 quotes for the exact same flight slot from different OTAs / direct channels
    data = [
        {"raw_quote_id": 1, "route_id": 1, "source_id": 1, "flight_number": "6E-101", "departure_datetime": dep_time, "advance_window_days": 7, "clean_total_fare": 5200.0},
        {"raw_quote_id": 2, "route_id": 1, "source_id": 1, "flight_number": "6E-101", "departure_datetime": dep_time, "advance_window_days": 7, "clean_total_fare": 4600.0},  # Lowest
        {"raw_quote_id": 3, "route_id": 1, "source_id": 1, "flight_number": "6E-101", "departure_datetime": dep_time, "advance_window_days": 7, "clean_total_fare": 5800.0},
        # A different flight
        {"raw_quote_id": 4, "route_id": 1, "source_id": 1, "flight_number": "6E-202", "departure_datetime": dep_time, "advance_window_days": 7, "clean_total_fare": 6100.0},
    ]

    df = pd.DataFrame(data)
    deduped = deduplicate_quotes_df(df)

    assert len(deduped) == 2
    retained_6e101 = deduped[deduped["flight_number"] == "6E-101"].iloc[0]
    assert retained_6e101["clean_total_fare"] == 4600.0
    assert retained_6e101["raw_quote_id"] == 2


def test_outlier_detection_flags_extreme_spikes_and_glitches():
    """Verify statistical and absolute outlier detection flags glitches and extreme price spikes."""
    data = [
        # Normal DEL-BOM fares around ~5000 INR
        {"raw_quote_id": 1, "route_id": 1, "advance_window_days": 7, "clean_total_fare": 4800.0},
        {"raw_quote_id": 2, "route_id": 1, "advance_window_days": 7, "clean_total_fare": 5100.0},
        {"raw_quote_id": 3, "route_id": 1, "advance_window_days": 7, "clean_total_fare": 4950.0},
        {"raw_quote_id": 4, "route_id": 1, "advance_window_days": 7, "clean_total_fare": 5300.0},
        {"raw_quote_id": 5, "route_id": 1, "advance_window_days": 7, "clean_total_fare": 5050.0},
        {"raw_quote_id": 6, "route_id": 1, "advance_window_days": 7, "clean_total_fare": 5200.0},
        # Outlier 1: Glitch 100 INR fare
        {"raw_quote_id": 7, "route_id": 1, "advance_window_days": 7, "clean_total_fare": 100.0},
        # Outlier 2: 150,000 INR extreme surge spike
        {"raw_quote_id": 8, "route_id": 1, "advance_window_days": 7, "clean_total_fare": 150000.0},
    ]

    df = pd.DataFrame(data)
    flagged = detect_outliers_df(df)

    outliers = flagged[flagged["is_outlier"] == True]
    normals = flagged[flagged["is_outlier"] == False]

    assert len(outliers) == 2
    assert set(outliers["raw_quote_id"]) == {7, 8}
    assert len(normals) == 6


@pytest.mark.asyncio
async def test_full_pipeline_with_mock_ingestion(db_session):
    """Verify complete end-to-end pipeline: seed -> mock ingestion -> cleaning -> processed quotes."""
    # 1. Seed database with routes and carriers
    seed_database(db=db_session)

    # 2. Run mock ingestion
    job, raw_quotes = await run_mock_ingestion(db_session, random_seed=42)
    assert job.status == "COMPLETED"
    assert job.total_scraped > 0
    assert len(raw_quotes) == job.total_scraped
    assert {q.collection_mode for q in raw_quotes} == {"MOCK"}
    assert {q.scraping_job_id for q in raw_quotes} == {job.id}

    # Verify raw quotes exist in DB
    db_raw_count = db_session.query(RawAirfareQuote).count()
    assert db_raw_count == len(raw_quotes)

    # 3. Process raw batch
    summary = process_raw_batch(db_session, job_id=job.id)
    assert summary["status"] == "success"
    assert summary["raw_quotes_count"] == len(raw_quotes)
    assert summary["processed_quotes_count"] > 0
    assert summary["clean_usable_count"] > 0

    # 4. Verify processed quotes in DB
    processed_count = db_session.query(ProcessedAirfareQuote).count()
    assert processed_count == summary["processed_quotes_count"]

    # Verify raw quotes were NOT deleted
    assert db_session.query(RawAirfareQuote).count() == db_raw_count


@pytest.mark.asyncio
async def test_live_ingestion_wires_akasa_first_without_network(db_session, monkeypatch):
    """Verify live ingestion uses Akasa first and maps the seeded QP source id."""
    seed_database(db=db_session)
    captured = {}

    class FakeSource:
        def __init__(self, source_name):
            self.config = type("Config", (), {"source_name": source_name})()

    class FakeOrchestrator:
        def __init__(self, sources, cooldown_seconds=900, source_id_by_name=None):
            captured["source_names"] = [source.config.source_name for source in sources]
            captured["source_id_by_name"] = source_id_by_name

        async def collect_quotes(
            self,
            origin,
            destination,
            departure_date,
            cabin_class,
            route_id,
            source_id,
            advance_window_days=None,
        ):
            captured["collect_args"] = {
                "origin": origin,
                "destination": destination,
                "departure_date": departure_date,
                "cabin_class": cabin_class,
                "route_id": route_id,
                "source_id": source_id,
                "advance_window_days": advance_window_days,
            }
            return SourceCollectionResult(
                quotes=[
                    RawAirfareQuoteCreate(
                        source_id=source_id,
                        route_id=route_id,
                        flight_number="QP1833",
                        departure_datetime=datetime.combine(departure_date, datetime.min.time(), tzinfo=timezone.utc),
                        arrival_datetime=None,
                        advance_window_days=advance_window_days,
                        base_fare=0.0,
                        taxes_fees=0.0,
                        total_fare=6530.0,
                        cabin_class=cabin_class,
                        scraped_at=datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc),
                    )
                ],
                attempts=[SourceAttempt("Akasa Air", SUCCESS, "success", 1)],
            )

    monkeypatch.setattr(ingestion_service, "AkasaWebsiteScraper", lambda: FakeSource("Akasa Air"))
    monkeypatch.setattr(ingestion_service, "AirIndiaWebsiteScraper", lambda: FakeSource("Air India"))
    monkeypatch.setattr(ingestion_service, "SourceOrchestrator", FakeOrchestrator)

    job, raw_quotes, summary = await ingestion_service.run_live_ingestion(
        db_session,
        collection_date=date(2026, 9, 4),
        advance_window_days=15,
    )

    akasa = db_session.query(Airline).filter(Airline.code == "QP").first()
    assert captured["source_names"] == ["Akasa Air", "Air India"]
    assert captured["source_id_by_name"]["Akasa Air"] == akasa.id
    assert captured["collect_args"]["source_id"] == akasa.id
    assert captured["collect_args"]["departure_date"] == date(2026, 9, 19)
    assert captured["collect_args"]["advance_window_days"] == 15
    assert raw_quotes[0].source_id == akasa.id
    assert raw_quotes[0].advance_window_days == 15
    assert raw_quotes[0].collection_mode == "LIVE"
    assert raw_quotes[0].scraping_job_id == job.id
    assert summary["advance_window_days"] == 15
    assert summary["departure_date"] == date(2026, 9, 19)
    assert job.status == "COMPLETED"
    assert summary["status"] == "success"


@pytest.mark.asyncio
async def test_live_ingestion_blocked_attempt_does_not_use_mock(db_session, monkeypatch):
    """Verify live failures do not silently fall back to synthetic data."""
    seed_database(db=db_session)
    captured = {}

    class FakeSource:
        def __init__(self, source_name):
            self.config = type("Config", (), {"source_name": source_name})()

    class FakeOrchestrator:
        def __init__(self, sources, cooldown_seconds=900, source_id_by_name=None):
            captured["source_names"] = [source.config.source_name for source in sources]

        async def collect_quotes(
            self,
            origin,
            destination,
            departure_date,
            cabin_class,
            route_id,
            source_id,
            advance_window_days=None,
        ):
            return SourceCollectionResult(
                quotes=[],
                attempts=[SourceAttempt("Akasa Air", "TEMPORARILY_BLOCKED", "captcha detected", 0)],
            )

    monkeypatch.setattr(ingestion_service, "AkasaWebsiteScraper", lambda: FakeSource("Akasa Air"))
    monkeypatch.setattr(ingestion_service, "AirIndiaWebsiteScraper", lambda: FakeSource("Air India"))
    monkeypatch.setattr(ingestion_service, "SourceOrchestrator", FakeOrchestrator)

    job, raw_quotes, summary = await ingestion_service.run_live_ingestion(
        db_session,
        collection_date=date(2026, 9, 4),
        advance_window_days=1,
    )

    assert captured["source_names"] == ["Akasa Air", "Air India"]
    assert raw_quotes == []
    assert job.status == "FAILED"
    assert summary["status"] == "failed"
    assert db_session.query(RawAirfareQuote).count() == 0


@pytest.mark.asyncio
async def test_live_ingestion_rejects_source_window_mismatch(db_session, monkeypatch):
    """Verify live insertion fails when a source returns the wrong requested window."""
    seed_database(db=db_session)

    class FakeSource:
        def __init__(self, source_name):
            self.config = type("Config", (), {"source_name": source_name})()

    class FakeOrchestrator:
        def __init__(self, sources, cooldown_seconds=900, source_id_by_name=None):
            pass

        async def collect_quotes(
            self,
            origin,
            destination,
            departure_date,
            cabin_class,
            route_id,
            source_id,
            advance_window_days=None,
        ):
            return SourceCollectionResult(
                quotes=[
                    RawAirfareQuoteCreate(
                        source_id=source_id,
                        route_id=route_id,
                        flight_number="QP1833",
                        departure_datetime=datetime.combine(departure_date, datetime.min.time(), tzinfo=timezone.utc),
                        arrival_datetime=None,
                        advance_window_days=0,
                        base_fare=0.0,
                        taxes_fees=0.0,
                        total_fare=6530.0,
                        cabin_class=cabin_class,
                        scraped_at=datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc),
                    )
                ],
                attempts=[SourceAttempt("Akasa Air", SUCCESS, "success", 1)],
            )

    monkeypatch.setattr(ingestion_service, "AkasaWebsiteScraper", lambda: FakeSource("Akasa Air"))
    monkeypatch.setattr(ingestion_service, "AirIndiaWebsiteScraper", lambda: FakeSource("Air India"))
    monkeypatch.setattr(ingestion_service, "SourceOrchestrator", FakeOrchestrator)

    job, raw_quotes, summary = await ingestion_service.run_live_ingestion(
        db_session,
        collection_date=date(2026, 9, 4),
        advance_window_days=1,
    )

    assert raw_quotes == []
    assert summary["status"] == "failed"
    assert "advance_window_days 0 != 1" in summary["validation_errors"][0]
    assert job.status == "FAILED"
    assert db_session.query(RawAirfareQuote).count() == 0


def test_ingest_raw_quotes_persists_provenance_and_job_source(db_session):
    """Verify raw quotes retain collection mode, source, and job/run association."""
    seed_database(db=db_session)
    route = db_session.query(Route).filter(Route.origin_code == "DEL", Route.destination_code == "BOM").first()
    akasa = db_session.query(Airline).filter(Airline.code == "QP").first()
    job = start_scraping_job(db_session, source_name="LiveWebsiteOrchestrator")

    raw_quotes = ingest_raw_quotes(
        db_session,
        [
            RawAirfareQuoteCreate(
                source_id=akasa.id,
                route_id=route.id,
                flight_number="QP1833",
                departure_datetime=datetime(2026, 9, 11, 6, 50, tzinfo=timezone.utc),
                arrival_datetime=datetime(2026, 9, 11, 9, 10, tzinfo=timezone.utc),
                advance_window_days=7,
                base_fare=5640.0,
                taxes_fees=890.0,
                total_fare=6530.0,
                cabin_class="ECONOMY",
                scraped_at=datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc),
            )
        ],
        job=job,
        collection_mode="LIVE",
    )

    persisted = raw_quotes[0]
    assert persisted.collection_mode == "LIVE"
    assert persisted.scraping_job_id == job.id
    assert persisted.scraping_job.source_name == "LiveWebsiteOrchestrator"
    assert persisted.airline_source.code == "QP"


def test_filter_duplicate_raw_quotes_skips_existing_live_same_day(db_session):
    """Verify controlled live insertion skips exact same-day duplicate observations."""
    seed_database(db=db_session)
    route = db_session.query(Route).filter(Route.origin_code == "DEL", Route.destination_code == "BOM").first()
    akasa = db_session.query(Airline).filter(Airline.code == "QP").first()
    job = start_scraping_job(db_session, source_name="LiveWebsiteOrchestrator")
    quote = RawAirfareQuoteCreate(
        source_id=akasa.id,
        route_id=route.id,
        flight_number="QP1833",
        departure_datetime=datetime(2026, 9, 11, 6, 50, tzinfo=timezone.utc),
        arrival_datetime=datetime(2026, 9, 11, 9, 10, tzinfo=timezone.utc),
        advance_window_days=7,
        base_fare=5640.0,
        taxes_fees=890.0,
        total_fare=6530.0,
        cabin_class="ECONOMY",
        scraped_at=datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc),
    )
    ingest_raw_quotes(db_session, [quote], job=job, collection_mode="LIVE")

    filtered, duplicate_count = filter_duplicate_raw_quotes(db_session, [quote], collection_mode="LIVE")

    assert filtered == []
    assert duplicate_count == 1


def test_provenance_survives_raw_to_processed_quote(db_session):
    """Verify processed observations can be traced back to raw provenance."""
    seed_database(db=db_session)
    route = db_session.query(Route).filter(Route.origin_code == "DEL", Route.destination_code == "BOM").first()
    akasa = db_session.query(Airline).filter(Airline.code == "QP").first()
    job = start_scraping_job(db_session, source_name="LiveWebsiteOrchestrator")
    raw_quotes = ingest_raw_quotes(
        db_session,
        [
            RawAirfareQuoteCreate(
                source_id=akasa.id,
                route_id=route.id,
                flight_number="QP1833",
                departure_datetime=datetime(2026, 9, 11, 6, 50, tzinfo=timezone.utc),
                arrival_datetime=datetime(2026, 9, 11, 9, 10, tzinfo=timezone.utc),
                advance_window_days=7,
                base_fare=5640.0,
                taxes_fees=890.0,
                total_fare=6530.0,
                cabin_class="ECONOMY",
                scraped_at=datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc),
            )
        ],
        job=job,
        collection_mode="LIVE",
    )

    processed = process_raw_batch(db_session, raw_quotes=raw_quotes, job_id=job.id)
    processed_quote = db_session.query(ProcessedAirfareQuote).one()

    assert processed["processed_quotes_count"] == 1
    assert processed_quote.raw_quote.collection_mode == "LIVE"
    assert processed_quote.raw_quote.scraping_job_id == job.id
    assert processed_quote.raw_quote.airline_source.name == "Akasa Air"


def test_quote_provenance_report_separates_mock_and_live_records(db_session):
    """Verify reporting groups observations by collection mode, source, and job."""
    seed_database(db=db_session)
    route = db_session.query(Route).filter(Route.origin_code == "DEL", Route.destination_code == "BOM").first()
    akasa = db_session.query(Airline).filter(Airline.code == "QP").first()
    mock_job = start_scraping_job(db_session, source_name="MockSyntheticEngine")
    live_job = start_scraping_job(db_session, source_name="LiveWebsiteOrchestrator")

    ingest_raw_quotes(
        db_session,
        [
            RawAirfareQuoteCreate(
                source_id=akasa.id,
                route_id=route.id,
                flight_number="QP-MOCK",
                departure_datetime=datetime(2026, 9, 11, 6, 50, tzinfo=timezone.utc),
                arrival_datetime=None,
                advance_window_days=7,
                base_fare=0.0,
                taxes_fees=0.0,
                total_fare=6100.0,
                cabin_class="ECONOMY",
                scraped_at=datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc),
            )
        ],
        job=mock_job,
        collection_mode="MOCK",
    )
    ingest_raw_quotes(
        db_session,
        [
            RawAirfareQuoteCreate(
                source_id=akasa.id,
                route_id=route.id,
                flight_number="QP1833",
                departure_datetime=datetime(2026, 9, 11, 6, 50, tzinfo=timezone.utc),
                arrival_datetime=None,
                advance_window_days=7,
                base_fare=0.0,
                taxes_fees=0.0,
                total_fare=6530.0,
                cabin_class="ECONOMY",
                scraped_at=datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc),
            )
        ],
        job=live_job,
        collection_mode="LIVE",
    )

    report = get_quote_provenance_report(db_session)

    assert {"mode": "MOCK", "source": "MockSyntheticEngine", "job_id": mock_job.id, "quote_count": 1} in report
    assert {"mode": "LIVE", "source": "Akasa Air", "job_id": live_job.id, "quote_count": 1} in report
    assert all(row["mode"] in {"MOCK", "LIVE"} for row in report)
