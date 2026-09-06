"""Integration tests for API v1 REST endpoints."""

import asyncio
import pytest
from datetime import date, datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from backend.app.db.base_class import Base
from backend.app.db.session import get_db
from backend.app.db.seed import seed_database
import backend.app.models  # Ensure all models are registered
from backend.app.services.ingestion_service import run_mock_ingestion
from backend.app.services.index_engine import calculate_composite_index
from backend.app.services.pipeline_service import process_raw_batch


@pytest.fixture(scope="module")
def api_test_db():
    """In-memory SQLite engine and session factory for isolated API tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Seed initial DGCA routes and airlines
    init_db = TestingSessionLocal()
    seed_database(db=init_db)
    init_db.close()

    yield TestingSessionLocal
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def api_client(api_test_db):
    """TestClient with dependency override pointing to isolated in-memory DB."""
    def override_get_db():
        db = api_test_db()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        test_client.testing_session_local = api_test_db
        yield test_client
    app.dependency_overrides.clear()


def _trigger_mock_pipeline(api_client: TestClient) -> dict:
    """Create isolated MOCK observations needed by API tests that inspect MOCK results."""
    db = api_client.testing_session_local()
    try:
        collection_date = date(2026, 9, 4)
        job, raw_quotes = asyncio.run(run_mock_ingestion(db, collection_date=collection_date, random_seed=42))
        batch = process_raw_batch(db, raw_quotes=raw_quotes, job_id=job.id)
        index = calculate_composite_index(db, collection_date, collection_mode="MOCK")
        return {
            "status": "success",
            "source": job.source_name,
            "collection_date": collection_date.isoformat(),
            "ingested_count": len(raw_quotes),
            "processed_quotes_count": batch["processed_quotes_count"],
            "clean_usable_count": batch["clean_usable_count"],
            "index_value": index.index_value if index else None,
            "ma_7d": index.ma_7d if index else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "collection_mode": "MOCK",
        }
    finally:
        db.close()


def test_index_latest_404_when_empty(api_client: TestClient):
    """Verify GET /api/v1/index/latest returns 404 when no index has been computed."""
    response = api_client.get("/api/v1/index/latest")
    assert response.status_code == 404
    data = response.json()
    assert "No LIVE index records found" in data["detail"]


def test_get_routes(api_client: TestClient):
    """Verify GET /api/v1/routes returns monitored DGCA routes with required fields."""
    response = api_client.get("/api/v1/routes")
    assert response.status_code == 200
    routes = response.json()

    assert isinstance(routes, list)
    assert len(routes) == 6  # 6 standard DGCA routes seeded

    del_bom = next((r for r in routes if r["route_key"] == "DEL-BOM"), None)
    assert del_bom is not None
    # Verify all required route properties
    assert del_bom["route_code"] == "DEL-BOM"
    assert del_bom["origin"] == "DEL"
    assert del_bom["origin_code"] == "DEL"
    assert del_bom["destination"] == "BOM"
    assert del_bom["destination_code"] == "BOM"
    assert del_bom["distance"] == 1148.0
    assert del_bom["passenger_market_weight"] == pytest.approx(0.294032, rel=1e-5)
    assert del_bom["dgca_weight"] == pytest.approx(0.294032, rel=1e-5)
    assert del_bom["is_active"] is True


def test_get_route_weights(api_client: TestClient):
    """Verify GET /api/v1/routes/weights returns DGCA passenger-traffic weights and coverage."""
    response = api_client.get("/api/v1/routes/weights")
    assert response.status_code == 200
    data = response.json()

    assert data["source"] == "DGCA Table 5.01 Indian City-Wise Passenger Traffic"
    assert data["traffic_period"] == "2024-25"
    assert data["directionality"] == "directional"
    assert data["coverage"] == {"available": 6, "total": 6, "percentage": 100.0}
    assert data["missing_routes"] == []
    assert data["unmapped_routes"] == []
    assert data["total_passenger_traffic"] == 11652577

    routes = {route["route_code"]: route for route in data["routes"]}
    assert set(routes) == {"DEL-BOM", "DEL-BLR", "BOM-BLR", "DEL-CCU", "BLR-HYD", "MAA-DEL"}
    assert routes["DEL-BOM"]["status"] == "AVAILABLE"
    assert routes["DEL-BOM"]["passenger_traffic"] == 3426228
    assert routes["DEL-BOM"]["weight"] == pytest.approx(0.294032, rel=1e-5)


def test_pipeline_trigger(api_client: TestClient, monkeypatch):
    """Verify POST /api/v1/pipeline/trigger uses the daily LIVE matrix adapter."""
    async def fake_daily_pipeline(**kwargs):
        return {
            "status": "SKIPPED",
            "job_id": 0,
            "source": "DailyLiveRouteWindowMatrix",
            "collection_date": date(2026, 9, 4),
            "ingested_count": 0,
            "processed_quotes_count": 0,
            "outliers_count": 0,
            "clean_usable_count": 0,
            "index_value": None,
            "ma_7d": None,
            "dod_change_pct": None,
            "collection_mode": "LIVE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    monkeypatch.setattr("backend.app.api.v1.endpoints.pipeline.run_daily_live_pipeline_trigger", fake_daily_pipeline)

    response = api_client.post(
        "/api/v1/pipeline/trigger",
        json={"collection_date": "2026-09-04", "random_seed": 42, "force_recalculate": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SKIPPED"
    assert data["source"] == "DailyLiveRouteWindowMatrix"
    assert data["collection_mode"] == "LIVE"
    assert data["collection_date"] == "2026-09-04"
    assert "timestamp" in data


def test_index_latest_after_trigger(api_client: TestClient):
    """Verify GET /api/v1/index/latest returns populated score after pipeline run."""
    _trigger_mock_pipeline(api_client)
    response = api_client.get("/api/v1/index/latest?collection_mode=MOCK")
    assert response.status_code == 200

    data = response.json()
    assert data["date"] == "2026-09-04"
    assert data["frequency"] == "daily"
    assert data["collection_mode"] == "MOCK"
    assert data["index_value"] > 0.0
    assert data["baseline_period"] == "2026-Q1"
    assert data["ma_7d"] is not None
    assert "calculated_at" in data


def test_index_historical(api_client: TestClient):
    """Verify GET /api/v1/index/historical returns time-series records."""
    _trigger_mock_pipeline(api_client)
    response = api_client.get("/api/v1/index/historical?collection_mode=MOCK")
    assert response.status_code == 200

    data = response.json()
    assert data["count"] >= 1
    assert data["frequency"] == "daily"
    assert data["collection_mode"] == "MOCK"
    assert isinstance(data["items"], list)
    assert len(data["items"]) >= 1

    first_item = data["items"][0]
    assert "date" in first_item
    assert first_item["collection_mode"] == "MOCK"
    assert "index_value" in first_item
    assert first_item["index_value"] > 0.0


def test_route_index_corridor_and_windows(api_client: TestClient):
    """Verify GET /api/v1/routes/{route_code}/index returns route index and advance-window breakdown."""
    _trigger_mock_pipeline(api_client)
    response = api_client.get("/api/v1/routes/DEL-BOM/index?target_date=2026-09-04&collection_mode=MOCK")
    assert response.status_code == 200

    data = response.json()
    assert data["route_key"] == "DEL-BOM"
    assert data["route_code"] == "DEL-BOM"
    assert data["origin"] == "DEL"
    assert data["destination"] == "BOM"
    assert data["distance"] == 1148.0
    assert data["dgca_weight"] == pytest.approx(0.294032, rel=1e-5)
    assert data["collection_mode"] == "MOCK"
    assert data["target_date"] == "2026-09-04"
    assert 80.0 <= data["route_index"] <= 130.0

    # Verify advance-window breakdown contains T+1, T+7, T+15, T+30, T+45
    windows = data["windows"]
    assert len(windows) == 5

    window_days = [w["advance_window_days"] for w in windows]
    assert window_days == [1, 7, 15, 30, 45]

    for w in windows:
        assert w["window_label"] == f"T+{w['advance_window_days']}"
        assert w["mean_fare"] > 0.0
        assert w["baseline_fare"] > 0.0
        assert w["sub_index"] > 0.0
        assert w["quotes_count"] > 0

    assert isinstance(data["historical_points"], list)
    assert len(data["historical_points"]) >= 1


def test_route_index_flexible_code_lookup(api_client: TestClient):
    """Verify GET /api/v1/routes/{route_code}/index handles variations (lowercase, concatenated)."""
    _trigger_mock_pipeline(api_client)

    # Lowercase with hyphen
    r_lower = api_client.get("/api/v1/routes/del-bom/index?collection_mode=MOCK")
    assert r_lower.status_code == 200
    assert r_lower.json()["route_key"] == "DEL-BOM"
    assert r_lower.json()["collection_mode"] == "MOCK"

    # Concatenated 6-letter
    r_concat = api_client.get("/api/v1/routes/DELBOM/index?collection_mode=MOCK")
    assert r_concat.status_code == 200
    assert r_concat.json()["route_key"] == "DEL-BOM"
    assert r_concat.json()["collection_mode"] == "MOCK"


def test_route_index_404_for_unknown_route(api_client: TestClient):
    """Verify GET /api/v1/routes/{route_code}/index returns 404 for nonexistent route."""
    response = api_client.get("/api/v1/routes/XYZ-ABC/index")
    assert response.status_code == 404
    assert "Route 'XYZ-ABC' not found" in response.json()["detail"]
