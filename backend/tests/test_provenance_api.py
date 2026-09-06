"""Tests for provenance and live-only read API endpoints."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base_class import Base
from backend.app.db.seed import seed_database
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.models.airline import Airline
from backend.app.models.quote import ProcessedAirfareQuote, RawAirfareQuote
from backend.app.models.route import Route
from backend.app.models.scraping_job import ScrapingJobLog
from backend.app.services.ingestion_service import finish_scraping_job, ingest_raw_quotes, start_scraping_job
from backend.app.services.pipeline_service import process_raw_batch
from backend.app.schemas.quote import RawAirfareQuoteCreate


@pytest.fixture(scope="function")
def provenance_client():
    """TestClient backed by a fresh in-memory provenance dataset."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestingSessionLocal()
    seed_database(db=db)
    _seed_provenance_quotes(db)
    db.close()

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def _seed_provenance_quotes(db):
    route = db.query(Route).filter(Route.origin_code == "DEL", Route.destination_code == "BOM").first()
    akasa = db.query(Airline).filter(Airline.code == "QP").first()
    air_india = db.query(Airline).filter(Airline.code == "AI").first()
    mock_job = start_scraping_job(db, source_name="MockSyntheticEngine")
    live_job = start_scraping_job(db, source_name="DailyLive:Akasa Air:DEL-BOM:T+7")
    failed_live_job = ScrapingJobLog(
        source_name="LiveWebsiteOrchestrator",
        status="FAILED",
        total_scraped=0,
        start_time=datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 5, 10, 1, tzinfo=timezone.utc),
        error_log="controlled failure",
    )
    db.add(failed_live_job)
    failed_daily_live_job = ScrapingJobLog(
        source_name="DailyLive:Akasa Air:MAA-DEL:T+7",
        status="FAILED",
        total_scraped=0,
        start_time=datetime(2026, 9, 5, 11, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 5, 11, 2, tzinfo=timezone.utc),
        error_log="classification=CAPTCHA_OR_BLOCK",
    )
    db.add(failed_daily_live_job)
    db.commit()

    mock_raw = ingest_raw_quotes(
        db,
        [
            _raw_quote(route.id, air_india.id, "AI-MOCK", 6100.0),
            _raw_quote(route.id, akasa.id, "QP-MOCK", 6200.0),
        ],
        job=mock_job,
        collection_mode="MOCK",
    )
    live_raw = ingest_raw_quotes(
        db,
        [
            _raw_quote(route.id, akasa.id, "QP1833", 6530.0),
            _raw_quote(route.id, akasa.id, "QP1119", 6530.0, hour=8, minute=40),
            _raw_quote(route.id, akasa.id, "QP1826", 11124.0, hour=19, minute=55),
        ],
        job=live_job,
        collection_mode="LIVE",
    )
    finish_scraping_job(db, mock_job, total_scraped=len(mock_raw), status="COMPLETED")
    finish_scraping_job(db, live_job, total_scraped=len(live_raw), status="COMPLETED")
    process_raw_batch(db, raw_quotes=mock_raw + live_raw, job_id=live_job.id)


def _raw_quote(route_id, source_id, flight_number, total_fare, hour=6, minute=50):
    return RawAirfareQuoteCreate(
        source_id=source_id,
        route_id=route_id,
        flight_number=flight_number,
        departure_datetime=datetime(2026, 9, 11, hour, minute, tzinfo=timezone.utc),
        arrival_datetime=datetime(2026, 9, 11, hour + 2, minute, tzinfo=timezone.utc),
        advance_window_days=7,
        base_fare=0.0,
        taxes_fees=0.0,
        total_fare=total_fare,
        cabin_class="ECONOMY",
        scraped_at=datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc),
    )


def test_provenance_summary_separates_mixed_modes(provenance_client: TestClient):
    response = provenance_client.get("/api/v1/provenance/summary")

    assert response.status_code == 200
    rows = response.json()["data"]
    assert {"collection_mode": "MOCK", "source": "MockSyntheticEngine", "job_id": 1, "quote_count": 2} in rows
    assert {"collection_mode": "LIVE", "source": "Akasa Air", "job_id": 2, "quote_count": 3} in rows


def test_live_summary_filters_live_only_and_excludes_mock(provenance_client: TestClient):
    response = provenance_client.get("/api/v1/provenance/live-summary")

    assert response.status_code == 200
    rows = response.json()["data"]
    assert len(rows) == 1
    assert rows[0]["route"] == "DEL-BOM"
    assert rows[0]["source"] == "Akasa Air"
    assert rows[0]["advance_window_days"] == 7
    assert rows[0]["quote_count"] == 3
    assert rows[0]["mean_fare"] == 8061.33
    assert rows[0]["min_fare"] == 6530.0
    assert rows[0]["max_fare"] == 11124.0


def test_live_summary_filters_route_t7_source_and_collection_date(provenance_client: TestClient):
    response = provenance_client.get(
        "/api/v1/provenance/live-summary",
        params={
            "route_code": "DELBOM",
            "advance_window_days": 7,
            "source": "QP",
            "collection_date": "2026-09-04",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"][0]["quote_count"] == 3


def test_live_summary_empty_result(provenance_client: TestClient):
    response = provenance_client.get("/api/v1/provenance/live-summary?collection_date=2026-09-06")

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_live_quotes_returns_only_live_rows(provenance_client: TestClient):
    response = provenance_client.get("/api/v1/provenance/live-quotes")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    flight_numbers = {item["flight_number"] for item in data["data"]}
    assert flight_numbers == {"QP1833", "QP1119", "QP1826"}
    assert "QP-MOCK" not in flight_numbers
    assert "AI-MOCK" not in flight_numbers


def test_live_quotes_filters_and_paginates(provenance_client: TestClient):
    response = provenance_client.get(
        "/api/v1/provenance/live-quotes",
        params={
            "route": "DEL-BOM",
            "source": "Akasa Air",
            "advance_window_days": 7,
            "collection_date": "2026-09-04",
            "limit": 2,
            "offset": 1,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["limit"] == 2
    assert data["offset"] == 1
    assert len(data["data"]) == 2
    assert all(item["route"] == "DEL-BOM" for item in data["data"])
    assert all(item["source"] == "Akasa Air" for item in data["data"])


def test_live_quotes_empty_result(provenance_client: TestClient):
    response = provenance_client.get("/api/v1/provenance/live-quotes?source=AI")

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["data"] == []


def test_provenance_jobs_show_mode_and_failed_jobs(provenance_client: TestClient):
    response = provenance_client.get("/api/v1/provenance/jobs")

    assert response.status_code == 200
    rows = response.json()["data"]
    assert any(row["job_id"] == 1 and row["collection_mode"] == "MOCK" and row["quote_count"] == 2 for row in rows)
    assert any(row["job_id"] == 2 and row["collection_mode"] == "LIVE" and row["quote_count"] == 3 for row in rows)
    assert any(row["job_id"] == 3 and row["collection_mode"] == "LIVE" and row["status"] == "FAILED" for row in rows)
    assert any(row["job_id"] == 4 and row["collection_mode"] == "LIVE" and row["status"] == "FAILED" and row["quote_count"] == 0 for row in rows)
    assert not any(row["job_id"] == 4 and row["collection_mode"] == "MOCK" for row in rows)


def test_invalid_filter_values(provenance_client: TestClient):
    bad_route_format = provenance_client.get("/api/v1/provenance/live-summary?route_code=DEL")
    missing_route = provenance_client.get("/api/v1/provenance/live-quotes?route=XYZ-ABC")
    missing_source = provenance_client.get("/api/v1/provenance/live-quotes?source=UnknownAir")
    bad_advance_window = provenance_client.get("/api/v1/provenance/live-quotes?advance_window_days=-1")

    assert bad_route_format.status_code == 422
    assert missing_route.status_code == 404
    assert missing_source.status_code == 404
    assert bad_advance_window.status_code == 422


def test_existing_endpoints_still_work_with_provenance_router(provenance_client: TestClient):
    assert provenance_client.get("/api/v1/routes").status_code == 200
    assert provenance_client.get("/api/v1/routes/DEL-BOM/index?target_date=2026-09-04").status_code == 200
    assert provenance_client.get("/api/v1/index/historical").status_code == 200

    latest = provenance_client.get("/api/v1/index/latest")
    assert latest.status_code in {200, 404}
