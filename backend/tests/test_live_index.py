"""Tests for non-persisted LIVE-only index analysis."""

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base_class import Base
from backend.app.data.route_basket import APPROVED_ADVANCE_WINDOWS
from backend.app.db.seed import seed_database
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.models.airline import Airline
from backend.app.models.index_value import AirfareIndexValue
from backend.app.models.quote import ProcessedAirfareQuote, RawAirfareQuote
from backend.app.models.route import Route
from backend.app.schemas.quote import RawAirfareQuoteCreate
from backend.app.services.index_engine import calculate_composite_index, get_route_baseline_fare
from backend.app.services.fare_reference_service import (
    PROTOTYPE_REFERENCE_COLLECTION_DATE,
    PROTOTYPE_REFERENCE_START_DATE,
    live_reference_status,
    validate_live_reference_completeness,
)
from backend.app.services.ingestion_service import finish_scraping_job, ingest_raw_quotes, start_scraping_job
from backend.app.services.live_index_service import calculate_live_only_index
from backend.app.services.pipeline_service import process_raw_batch


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


@pytest.fixture(scope="function")
def live_index_client(db_session):
    """TestClient using the live-index fixture database."""
    bind = db_session.get_bind()
    Session = sessionmaker(autocommit=False, autoflush=False, bind=bind)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _quote(route, source, dep_date, window, fare, flight_number, collection_date=date(2026, 9, 4)):
    dep_dt = datetime.combine(dep_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=window % 23)
    return RawAirfareQuoteCreate(
        source_id=source.id,
        route_id=route.id,
        flight_number=flight_number,
        departure_datetime=dep_dt,
        arrival_datetime=dep_dt + timedelta(hours=2),
        advance_window_days=window,
        base_fare=0.0,
        taxes_fees=0.0,
        total_fare=fare,
        cabin_class="ECONOMY",
        scraped_at=datetime.combine(collection_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10),
    )


def _seed_partial_live_dataset(db):
    route = db.query(Route).filter(Route.origin_code == "DEL", Route.destination_code == "BOM").first()
    akasa = db.query(Airline).filter(Airline.code == "QP").first()
    air_india = db.query(Airline).filter(Airline.code == "AI").first()
    live_job = start_scraping_job(db, source_name="LiveWebsiteOrchestrator")
    mock_job = start_scraping_job(db, source_name="MockSyntheticEngine")
    dep_date = date(2026, 9, 11)

    live_raw = ingest_raw_quotes(
        db,
        [
            _quote(route, akasa, dep_date, 7, 6530.0, "QP1833"),
            _quote(route, akasa, dep_date, 7, 6530.0, "QP1119"),
            _quote(route, akasa, dep_date, 7, 11124.0, "QP1826"),
        ],
        job=live_job,
        collection_mode="LIVE",
    )
    mock_raw = ingest_raw_quotes(
        db,
        [
            _quote(route, akasa, dep_date, 7, 1000.0, "QP-MOCK"),
            _quote(route, air_india, dep_date, 7, 20000.0, "AI-MOCK"),
        ],
        job=mock_job,
        collection_mode="MOCK",
    )
    finish_scraping_job(db, live_job, len(live_raw), "COMPLETED")
    finish_scraping_job(db, mock_job, len(mock_raw), "COMPLETED")
    process_raw_batch(db, raw_quotes=live_raw + mock_raw, job_id=live_job.id)
    return route, akasa, air_india


def _seed_complete_live_matrix(db, collection_date=PROTOTYPE_REFERENCE_START_DATE, fare_multiplier=1.0, prefix="QP"):
    akasa = db.query(Airline).filter(Airline.code == "QP").first()
    routes = db.query(Route).filter(Route.is_active == True).order_by(Route.id.asc()).all()
    live_job = start_scraping_job(db, source_name="LiveWebsiteOrchestrator")
    quotes = []
    for route in routes:
        for window in APPROVED_ADVANCE_WINDOWS:
            dep_date = collection_date + timedelta(days=window)
            route_key = route.route_key
            baseline = get_route_baseline_fare(route_key, window)
            quotes.append(
                _quote(
                    route,
                    akasa,
                    dep_date,
                    window,
                    baseline * fare_multiplier,
                    f"{prefix}-{route.id}-{window}",
                    collection_date,
                )
            )
    raw = ingest_raw_quotes(db, quotes, job=live_job, collection_mode="LIVE")
    finish_scraping_job(db, live_job, len(raw), "COMPLETED")
    process_raw_batch(db, raw_quotes=raw, job_id=live_job.id)


def _seed_complete_mock_matrix(db, fare_multiplier=10.0):
    akasa = db.query(Airline).filter(Airline.code == "QP").first()
    routes = db.query(Route).filter(Route.is_active == True).order_by(Route.id.asc()).all()
    mock_job = start_scraping_job(db, source_name="MockSyntheticEngine")
    collection_date = date(2026, 9, 4)
    quotes = []
    for route in routes:
        for window in APPROVED_ADVANCE_WINDOWS:
            dep_date = collection_date + timedelta(days=window)
            baseline = get_route_baseline_fare(route.route_key, window)
            quotes.append(
                _quote(
                    route,
                    akasa,
                    dep_date,
                    window,
                    baseline * fare_multiplier,
                    f"MOCK-{route.id}-{window}",
                    collection_date,
                )
            )
    raw = ingest_raw_quotes(db, quotes, job=mock_job, collection_mode="MOCK")
    finish_scraping_job(db, mock_job, len(raw), "COMPLETED")
    process_raw_batch(db, raw_quotes=raw, job_id=mock_job.id)


def test_live_only_index_includes_live_and_excludes_mock(db_session):
    route, akasa, _ = _seed_partial_live_dataset(db_session)

    result = calculate_live_only_index(db_session, collection_date=date(2026, 9, 4), route=route, advance_window_days=7)

    assert result.collection_mode == "LIVE"
    assert result.live_quote_count == 3
    assert result.sources_represented == ["Akasa Air"]
    assert result.reference_status == "INSUFFICIENT_REFERENCE_DATA"
    assert result.index_value is None
    assert result.route_values == []


def test_changing_mock_fares_does_not_change_live_index(db_session):
    _seed_complete_live_matrix(db_session, collection_date=PROTOTYPE_REFERENCE_START_DATE, fare_multiplier=1.0, prefix="QP-REF")
    _seed_complete_live_matrix(db_session, collection_date=date(2026, 9, 6), fare_multiplier=1.2, prefix="QP-CURRENT")
    _seed_complete_mock_matrix(db_session, fare_multiplier=25.0)
    route = db_session.query(Route).filter(Route.origin_code == "DEL", Route.destination_code == "BOM").first()

    before = calculate_live_only_index(
        db_session,
        collection_date=date(2026, 9, 6),
        route=route,
        advance_window_days=7,
    )
    before_index = before.route_values[0].route_index

    mock_processed = (
        db_session.query(ProcessedAirfareQuote)
        .join(RawAirfareQuote, ProcessedAirfareQuote.raw_quote_id == RawAirfareQuote.id)
        .filter(RawAirfareQuote.collection_mode == "MOCK")
        .all()
    )
    for quote in mock_processed:
        quote.clean_total_fare = 999999.0
    db_session.commit()

    after = calculate_live_only_index(
        db_session,
        collection_date=date(2026, 9, 6),
        route=route,
        advance_window_days=7,
    )

    assert mock_processed
    assert after.route_values[0].route_index == before_index


def test_changing_live_fares_changes_live_index(db_session):
    _seed_complete_live_matrix(db_session, collection_date=PROTOTYPE_REFERENCE_START_DATE, fare_multiplier=1.0, prefix="QP-REF")
    _seed_complete_live_matrix(db_session, collection_date=date(2026, 9, 6), fare_multiplier=1.2, prefix="QP-CURRENT")
    route = db_session.query(Route).filter(Route.origin_code == "DEL", Route.destination_code == "BOM").first()

    before = calculate_live_only_index(
        db_session,
        collection_date=date(2026, 9, 6),
        route=route,
        advance_window_days=7,
    )
    before_index = before.route_values[0].route_index

    live_processed = (
        db_session.query(ProcessedAirfareQuote)
        .join(RawAirfareQuote, ProcessedAirfareQuote.raw_quote_id == RawAirfareQuote.id)
        .filter(RawAirfareQuote.collection_mode == "LIVE")
        .filter(RawAirfareQuote.scraped_at >= datetime(2026, 9, 6, tzinfo=timezone.utc))
        .all()
    )
    for quote in live_processed:
        quote.clean_total_fare *= 1.5
    db_session.commit()

    after = calculate_live_only_index(
        db_session,
        collection_date=date(2026, 9, 6),
        route=route,
        advance_window_days=7,
    )

    assert live_processed
    assert after.route_values[0].route_index > before_index


def test_mock_only_route_window_is_missing_from_live_coverage(db_session):
    _seed_partial_live_dataset(db_session)
    del_blr = db_session.query(Route).filter(Route.origin_code == "DEL", Route.destination_code == "BLR").first()
    akasa = db_session.query(Airline).filter(Airline.code == "QP").first()
    mock_job = start_scraping_job(db_session, source_name="MockSyntheticEngine")
    raw = ingest_raw_quotes(
        db_session,
        [_quote(del_blr, akasa, date(2026, 9, 19), 15, 12345.0, "MOCK-ONLY-WINDOW")],
        job=mock_job,
        collection_mode="MOCK",
    )
    finish_scraping_job(db_session, mock_job, len(raw), "COMPLETED")
    process_raw_batch(db_session, raw_quotes=raw, job_id=mock_job.id)

    result = calculate_live_only_index(
        db_session,
        collection_date=date(2026, 9, 4),
        route=del_blr,
        advance_window_days=15,
    )

    assert result.status == "INSUFFICIENT_COVERAGE"
    assert result.coverage.expected_route_window_combinations == 1
    assert result.coverage.observed_route_window_combinations == 0
    assert result.live_quote_count == 0
    assert result.route_values == []


def test_live_only_national_index_reports_insufficient_coverage(db_session):
    _seed_partial_live_dataset(db_session)

    result = calculate_live_only_index(db_session, collection_date=date(2026, 9, 4))

    assert result.status == "INSUFFICIENT_COVERAGE"
    assert result.index_value is None
    assert result.coverage.expected_route_window_combinations == 30
    assert result.coverage.observed_route_window_combinations == 1
    assert result.coverage.coverage_pct == 3.33


def test_reference_completeness_reports_missing_live_cells_without_fabrication(db_session):
    _seed_partial_live_dataset(db_session)

    completeness = validate_live_reference_completeness(db_session, date(2026, 9, 4))

    assert completeness.reference_date == date(2026, 9, 4)
    assert completeness.expected_cells == 30
    assert completeness.valid_live_cells == 1
    assert len(completeness.missing_cells) == 29
    assert "DEL-BOM:T+7" not in completeness.missing_cells
    assert completeness.complete is False
    assert completeness.status == "INCOMPLETE"


def test_reference_completeness_ignores_mock_only_cells_and_failed_jobs(db_session):
    _seed_partial_live_dataset(db_session)
    _seed_complete_mock_matrix(db_session, fare_multiplier=1.0)

    completeness = validate_live_reference_completeness(db_session, date(2026, 9, 4))

    assert completeness.expected_cells == 30
    assert completeness.valid_live_cells == 1
    assert completeness.complete is False


def test_reference_collection_date_is_explicit_and_fixed(db_session):
    assert PROTOTYPE_REFERENCE_COLLECTION_DATE == date(2026, 9, 5)

    status = live_reference_status(db_session)

    assert status.status == "INSUFFICIENT_REFERENCE_DATA"
    assert status.observed_route_window_combinations == 0


def test_complete_live_reference_period_becomes_available(db_session):
    _seed_complete_live_matrix(db_session, collection_date=PROTOTYPE_REFERENCE_COLLECTION_DATE, fare_multiplier=1.0)

    completeness = validate_live_reference_completeness(db_session, PROTOTYPE_REFERENCE_COLLECTION_DATE)
    status = live_reference_status(db_session)

    assert completeness.expected_cells == 30
    assert completeness.valid_live_cells == 30
    assert completeness.missing_cells == []
    assert completeness.complete is True
    assert status.is_available


def test_live_composite_index_refuses_insufficient_coverage_and_does_not_persist(db_session):
    _seed_partial_live_dataset(db_session)

    index_record = calculate_composite_index(db_session, date(2026, 9, 4), collection_mode="LIVE")

    live_index_count = (
        db_session.query(AirfareIndexValue)
        .filter(AirfareIndexValue.collection_mode == "LIVE")
        .count()
    )
    assert index_record is None
    assert live_index_count == 0


def test_live_coverage_counts_route_windows_not_individual_quotes(db_session):
    route = db_session.query(Route).filter(Route.origin_code == "DEL", Route.destination_code == "BOM").first()
    akasa = db_session.query(Airline).filter(Airline.code == "QP").first()
    live_job = start_scraping_job(db_session, source_name="LiveWebsiteOrchestrator")
    collection_date = date(2026, 9, 5)
    dep_date = date(2026, 9, 6)
    raw = ingest_raw_quotes(
        db_session,
        [
            _quote(route, akasa, dep_date, 1, 6500.0 + index, f"QP-{index}", collection_date)
            for index in range(7)
        ],
        job=live_job,
        collection_mode="LIVE",
    )
    finish_scraping_job(db_session, live_job, len(raw), "COMPLETED")
    process_raw_batch(db_session, raw_quotes=raw, job_id=live_job.id)

    result = calculate_live_only_index(db_session, collection_date=collection_date)

    assert result.live_quote_count == 7
    assert result.coverage.expected_route_window_combinations == 30
    assert result.coverage.observed_route_window_combinations == 1
    assert result.coverage.coverage_pct == 3.33


def test_live_only_route_window_source_filter_can_reach_sufficient_scope(db_session):
    _seed_complete_live_matrix(db_session, collection_date=PROTOTYPE_REFERENCE_START_DATE, fare_multiplier=1.0, prefix="QP-REF")
    route = db_session.query(Route).filter(Route.origin_code == "DEL", Route.destination_code == "BOM").first()
    akasa = db_session.query(Airline).filter(Airline.code == "QP").first()

    result = calculate_live_only_index(
        db_session,
        collection_date=PROTOTYPE_REFERENCE_START_DATE,
        route=route,
        advance_window_days=7,
        source=akasa,
    )

    assert result.status == "SUFFICIENT_COVERAGE"
    assert result.index_scope == "FILTERED"
    assert result.index_value == result.route_values[0].route_index
    assert result.coverage.expected_route_window_combinations == 1
    assert result.coverage.observed_route_window_combinations == 1


def test_live_only_source_filter_empty_when_source_has_only_mock(db_session):
    _, _, air_india = _seed_partial_live_dataset(db_session)

    result = calculate_live_only_index(db_session, collection_date=date(2026, 9, 4), source=air_india)

    assert result.status == "INSUFFICIENT_COVERAGE"
    assert result.live_quote_count == 0
    assert result.route_values == []


def test_live_only_origin_destination_filters_keep_live_scope(db_session):
    _seed_complete_live_matrix(db_session, collection_date=PROTOTYPE_REFERENCE_START_DATE, fare_multiplier=1.0, prefix="QP-REF")

    origin_result = calculate_live_only_index(db_session, collection_date=PROTOTYPE_REFERENCE_START_DATE, origin_code="DEL")
    destination_result = calculate_live_only_index(
        db_session,
        collection_date=PROTOTYPE_REFERENCE_START_DATE,
        origin_code="DEL",
        destination_code="BOM",
    )
    empty_result = calculate_live_only_index(db_session, collection_date=PROTOTYPE_REFERENCE_START_DATE, destination_code="BLR", source=db_session.query(Airline).filter(Airline.code == "AI").first())

    assert origin_result.collection_mode == "LIVE"
    assert origin_result.index_scope == "FILTERED"
    assert origin_result.coverage.expected_route_window_combinations == 15
    assert origin_result.coverage.observed_route_window_combinations == 15
    assert origin_result.sources_represented == ["Akasa Air"]

    assert destination_result.coverage.expected_route_window_combinations == 5
    assert destination_result.coverage.observed_route_window_combinations == 5
    assert destination_result.route_values[0].route == "DEL-BOM"

    assert empty_result.coverage.expected_route_window_combinations == 10
    assert empty_result.coverage.observed_route_window_combinations == 0
    assert empty_result.live_quote_count == 0
    assert empty_result.route_values == []


def test_live_only_complete_matrix_can_calculate_national_index(db_session):
    _seed_complete_live_matrix(db_session)

    result = calculate_live_only_index(db_session, collection_date=PROTOTYPE_REFERENCE_START_DATE)

    assert result.status == "SUFFICIENT_COVERAGE"
    assert result.coverage.expected_route_window_combinations == 30
    assert result.coverage.observed_route_window_combinations == 30
    assert result.coverage.coverage_pct == 100.0
    assert result.index_value == 100.0


def test_live_composite_index_excludes_mock_rows(db_session):
    _seed_complete_live_matrix(db_session)
    _seed_complete_mock_matrix(db_session, fare_multiplier=25.0)

    index_record = calculate_composite_index(db_session, PROTOTYPE_REFERENCE_START_DATE, collection_mode="LIVE")

    assert index_record is not None
    assert index_record.collection_mode == "LIVE"
    assert index_record.index_value == 100.0


def test_live_index_api_and_existing_index_endpoints(live_index_client: TestClient, db_session):
    _seed_complete_live_matrix(db_session)
    calculate_composite_index(db_session, PROTOTYPE_REFERENCE_START_DATE, collection_mode="LIVE")

    live_response = live_index_client.get("/api/v1/index/live?collection_date=2026-09-05")
    latest_response = live_index_client.get("/api/v1/index/latest")
    route_response = live_index_client.get("/api/v1/routes/DEL-BOM/index?target_date=2026-09-05")

    assert live_response.status_code == 200
    assert live_response.json()["status"] == "SUFFICIENT_COVERAGE"
    assert live_response.json()["live_quote_count"] == 30
    assert latest_response.status_code == 200
    assert latest_response.json()["collection_mode"] == "LIVE"
    assert latest_response.json()["index_value"] is not None
    assert route_response.status_code == 200
    assert route_response.json()["route_key"] == "DEL-BOM"
    assert route_response.json()["collection_mode"] == "LIVE"


def test_live_index_api_filters_and_invalid_values(live_index_client: TestClient, db_session):
    _seed_complete_live_matrix(db_session)

    filtered = live_index_client.get(
        "/api/v1/index/live?collection_date=2026-09-05&route_code=DELBOM&advance_window_days=7&source=QP"
    )
    scoped = live_index_client.get(
        "/api/v1/index/live?collection_date=2026-09-05&origin=DEL&destination=BOM&source=QP"
    )
    missing_source = live_index_client.get("/api/v1/index/live?source=UnknownAir")
    bad_route = live_index_client.get("/api/v1/index/live?route_code=DEL")

    assert filtered.status_code == 200
    assert filtered.json()["status"] == "SUFFICIENT_COVERAGE"
    assert filtered.json()["routes_represented"] == 1
    assert filtered.json()["advance_windows_represented"] == 1
    assert scoped.status_code == 200
    assert scoped.json()["coverage"]["expected_route_window_combinations"] == 5
    assert scoped.json()["coverage"]["observed_route_window_combinations"] == 5
    assert missing_source.status_code == 404
    assert bad_route.status_code == 422


def test_route_index_source_filter_and_filter_options(live_index_client: TestClient, db_session):
    _seed_partial_live_dataset(db_session)

    route_response = live_index_client.get("/api/v1/routes/DEL-BOM/index?target_date=2026-09-04&source=QP")
    no_live_for_source = live_index_client.get("/api/v1/routes/DEL-BOM/index?target_date=2026-09-04&source=AI")
    live_options = live_index_client.get("/api/v1/filters/options?collection_mode=LIVE")
    mock_options = live_index_client.get("/api/v1/filters/options?collection_mode=MOCK")

    assert route_response.status_code == 200
    assert route_response.json()["collection_mode"] == "LIVE"
    assert [window["advance_window_days"] for window in route_response.json()["windows"]] == [7]
    assert all(window["quotes_count"] > 0 for window in route_response.json()["windows"])

    assert no_live_for_source.status_code == 404

    assert live_options.status_code == 200
    live_data = live_options.json()
    assert live_data["collection_mode"] == "LIVE"
    assert {"value": "DEL", "label": "DEL", "quote_count": 3} in live_data["origins"]
    assert {"value": "BOM", "label": "BOM", "quote_count": 3} in live_data["destinations"]
    assert live_data["airlines"] == [{"value": "QP", "label": "Akasa Air", "quote_count": 3}]

    assert mock_options.status_code == 200
    mock_airlines = {item["value"] for item in mock_options.json()["airlines"]}
    assert mock_airlines == {"AI", "QP"}


def test_route_index_historical_points_are_recomputed_per_collection_date(live_index_client: TestClient, db_session):
    _seed_complete_live_matrix(db_session, collection_date=PROTOTYPE_REFERENCE_START_DATE, fare_multiplier=1.0, prefix="QP-REF")
    route = db_session.query(Route).filter(Route.origin_code == "DEL", Route.destination_code == "BOM").first()
    akasa = db_session.query(Airline).filter(Airline.code == "QP").first()
    live_job = start_scraping_job(db_session, source_name="DailyLive:Akasa Air:DEL-BOM:T+7")
    baseline = get_route_baseline_fare("DEL-BOM", 7)
    raw = ingest_raw_quotes(
        db_session,
        [
            _quote(route, akasa, date(2026, 9, 13), 7, baseline * 1.2, "QP-HIST-2", date(2026, 9, 6)),
        ],
        job=live_job,
        collection_mode="LIVE",
    )
    finish_scraping_job(db_session, live_job, len(raw), "COMPLETED")
    process_raw_batch(db_session, raw_quotes=raw, job_id=live_job.id)

    response = live_index_client.get("/api/v1/routes/DEL-BOM/index?collection_mode=LIVE")

    assert response.status_code == 200
    points = response.json()["historical_points"]
    by_date = {point["date"]: point["route_index"] for point in points}
    assert by_date["2026-09-05"] == 100.0
    assert by_date["2026-09-06"] == 120.0
    assert by_date["2026-09-05"] != by_date["2026-09-06"]
