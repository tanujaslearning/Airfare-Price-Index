"""Unit tests for Airfare Price Index calculation engine, DGCA weighting, and rolling metrics."""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base_class import Base
from backend.app.models.route import Route
from backend.app.models.airline import Airline
from backend.app.models.quote import RawAirfareQuote, ProcessedAirfareQuote
from backend.app.models.index_value import AirfareIndexValue
from backend.app.db.seed import seed_database

from backend.app.services.ingestion_service import run_mock_ingestion
from backend.app.services.cleaning_service import clean_and_normalize_raw_quotes
from backend.app.services.pipeline_service import process_raw_batch
from backend.app.services.index_engine import (
    get_route_baseline_fare,
    calculate_route_indices,
    calculate_composite_index,
    run_pipeline_and_calculate_index,
)
from backend.app.services.collection_dates import collection_date_from_timestamp
from backend.app.services.fare_reference_service import (
    OFFICIAL_CPI_INDEX_REFERENCE,
    OFFICIAL_CPI_PRICE_REFERENCE_PERIOD,
    OFFICIAL_CPI_WEIGHT_REFERENCE_PERIOD,
    PROTOTYPE_REFERENCE_METHOD,
    PROTOTYPE_REFERENCE_START_DATE,
    legacy_assumption_reference_fare,
    live_reference_status,
)
from backend.app.services.dgca_route_weights import calculate_dgca_route_weights


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


def test_baseline_fare_lookup_and_normalization():
    """Verify the legacy helper is explicitly retained for MOCK/dev compatibility."""
    del_bom_t7_base = get_route_baseline_fare("DEL-BOM", 7)
    assert del_bom_t7_base == legacy_assumption_reference_fare("DEL-BOM", 7)
    assert del_bom_t7_base > 4000.0

    # If observed fare equals exact base fare, sub-index is 100.0
    observed_fare = del_bom_t7_base
    sub_index = (observed_fare / del_bom_t7_base) * 100.0
    assert sub_index == 100.0

    # If observed fare is 10% higher, sub-index is 110.0
    observed_higher = del_bom_t7_base * 1.10
    sub_index_higher = (observed_higher / del_bom_t7_base) * 100.0
    assert round(sub_index_higher, 1) == 110.0


def test_reference_metadata_distinguishes_cpi_from_prototype_fare_reference():
    """Verify APIx does not treat CPI 2024=100 as a route/window rupee baseline."""
    assert OFFICIAL_CPI_INDEX_REFERENCE == "2024 = 100"
    assert OFFICIAL_CPI_PRICE_REFERENCE_PERIOD == "calendar year 2024"
    assert OFFICIAL_CPI_WEIGHT_REFERENCE_PERIOD == "HCES 2023-24"
    assert PROTOTYPE_REFERENCE_METHOD == "OBSERVED_LIVE_FIXED_REFERENCE_PERIOD"
    assert PROTOTYPE_REFERENCE_START_DATE != date(2024, 1, 1)


def test_dgca_weighting_math(db_session):
    """Verify DGCA passenger traffic normalizes to route weights."""
    seed_database(db=db_session)
    routes = db_session.query(Route).filter(Route.is_active == True).order_by(Route.id).all()
    weight_result = calculate_dgca_route_weights(routes)

    weights = np.array([route["weight"] for route in weight_result["routes"]])
    indices = np.array([104.0, 98.0, 102.0, 100.0, 95.0, 105.0])

    expected_composite = np.sum(weights * indices) / np.sum(weights)
    assert weight_result["coverage"] == {"available": 6, "total": 6, "percentage": 100.0}
    assert round(float(np.sum(weights)), 6) == 1.0
    assert round(expected_composite, 2) == 101.16


def test_dgca_route_weights_missing_and_unmapped(monkeypatch):
    """Verify missing and unmapped routes do not receive fabricated weights."""
    from backend.app.data import dgca_route_weights as weight_data

    routes = [
        Route(origin_code="DEL", destination_code="BOM", dgca_weight=0.0, is_active=True),
        Route(origin_code="AAA", destination_code="BBB", dgca_weight=0.0, is_active=True),
        Route(origin_code="CCC", destination_code="DDD", dgca_weight=0.0, is_active=True),
    ]
    missing_record = weight_data.DgcaRouteWeightRecord(
        route_code="AAA-BBB",
        origin="AAA",
        destination="BBB",
        dgca_route_identifier=None,
        passenger_traffic=None,
        traffic_period=None,
        source="DGCA",
        source_reference=None,
        directionality=None,
        status="MISSING",
    )
    monkeypatch.setitem(weight_data.DGCA_ROUTE_WEIGHTS, "AAA-BBB", missing_record)

    result = calculate_dgca_route_weights(routes)
    by_route = {route["route_code"]: route for route in result["routes"]}

    assert result["coverage"] == {"available": 1, "total": 3, "percentage": 33.33}
    assert result["missing_routes"] == ["AAA-BBB"]
    assert result["unmapped_routes"] == ["CCC-DDD"]
    assert by_route["DEL-BOM"]["weight"] == 1.0
    assert by_route["AAA-BBB"]["weight"] is None
    assert by_route["CCC-DDD"]["weight"] is None


@pytest.mark.asyncio
async def test_end_to_end_index_engine_pipeline(db_session):
    """Verify full workflow: seed -> mock ingest -> clean & normalize -> calculate index."""
    # 1. Seed routes and carriers
    seed_database(db=db_session)
    today = date(2026, 9, 1)

    # 2. Ingest mock quotes for today
    job, raw_quotes = await run_mock_ingestion(db_session, collection_date=today, random_seed=42)
    assert len(raw_quotes) > 0

    # 3. Clean raw quotes into processed quotes
    batch_res = process_raw_batch(db_session, raw_quotes=raw_quotes, job_id=job.id)
    assert batch_res["clean_usable_count"] > 0

    # 4. Calculate route-level sub-indices
    route_indices_df = calculate_route_indices(db_session, today, collection_mode="MOCK")
    assert not route_indices_df.empty
    assert len(route_indices_df) == 6  # All 6 seed routes present
    assert set(route_indices_df["collection_mode"]) == {"MOCK"}

    # Verify each route index is in a realistic corridor (80.0 to 125.0)
    for _, row in route_indices_df.iterrows():
        assert 80.0 <= row["route_index"] <= 130.0

    # 5. Calculate composite national index
    index_record = calculate_composite_index(db_session, today, collection_mode="MOCK")
    assert index_record is not None
    assert index_record.date == today
    assert index_record.frequency == "daily"
    assert index_record.collection_mode == "MOCK"
    assert 90.0 <= index_record.index_value <= 120.0
    assert index_record.ma_7d == index_record.index_value  # Day 1: 7-day MA equals day index
    assert index_record.dod_change_pct is None  # Day 1: No previous day


def test_rolling_indicators_multi_day(db_session):
    """Verify 7-day MA, 30-day MA, and DoD percentage change across consecutive days."""
    # Insert mock historical index values
    base_date = date(2026, 8, 25)
    historical_scores = [100.0, 102.0, 101.0, 103.0, 105.0, 104.0]

    for i, score in enumerate(historical_scores):
        d = base_date + timedelta(days=i)
        rec = AirfareIndexValue(
            date=d,
            frequency="daily",
            collection_mode="MOCK",
            index_value=score,
            baseline_period="2026-Q1",
        )
        db_session.add(rec)
    db_session.commit()

    # Calculate index for next day (2026-08-31)
    target_date = base_date + timedelta(days=6)  # Day 7

    # Create dummy route and processed quote for target_date
    route = Route(origin_code="DEL", destination_code="BOM", dgca_weight=1.0, is_active=True)
    db_session.add(route)
    db_session.commit()

    base_fare_del_bom = get_route_baseline_fare("DEL-BOM", 7)
    raw_quote = RawAirfareQuote(
        route_id=route.id,
        flight_number="MOCK-ROLLING",
        departure_datetime=datetime.combine(target_date + timedelta(days=7), datetime.min.time(), tzinfo=timezone.utc),
        advance_window_days=7,
        base_fare=0.0,
        taxes_fees=0.0,
        total_fare=base_fare_del_bom * 1.08,
        cabin_class="ECONOMY",
        collection_mode="MOCK",
        scraped_at=datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc),
    )
    db_session.add(raw_quote)
    db_session.commit()

    proc_quote = ProcessedAirfareQuote(
        raw_quote_id=raw_quote.id,
        route_id=route.id,
        advance_window_days=7,
        clean_total_fare=base_fare_del_bom * 1.08,  # +8% above base
        is_outlier=False,
        processed_at=datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc),
    )
    db_session.add(proc_quote)
    db_session.commit()

    # Run composite calculation
    index_res = calculate_composite_index(db_session, target_date, collection_mode="MOCK")
    assert index_res is not None
    assert index_res.collection_mode == "MOCK"
    assert round(index_res.index_value, 1) == 108.0

    # DoD Change: (108.0 - 104.0) / 104.0 * 100 = +3.85%
    assert round(index_res.dod_change_pct, 2) == 3.85

    # 7-day MA: mean of [108.0, 104.0, 105.0, 103.0, 101.0, 102.0, 100.0] = 723 / 7 = 103.29
    assert round(index_res.ma_7d, 2) == 103.29


def test_composite_index_uses_only_available_dgca_weights(db_session):
    """Verify unweighted routes are reported out of national aggregation, not equal-weighted."""
    target_date = date(2026, 9, 4)
    available_route = Route(origin_code="DEL", destination_code="BOM", dgca_weight=0.0, is_active=True)
    unmapped_route = Route(origin_code="AAA", destination_code="BBB", dgca_weight=0.0, is_active=True)
    db_session.add_all([available_route, unmapped_route])
    db_session.commit()

    available_base = get_route_baseline_fare("DEL-BOM", 7)
    unmapped_base = get_route_baseline_fare("AAA-BBB", 7)
    for route, fare, flight in [
        (available_route, available_base, "MOCK-DGCA"),
        (unmapped_route, unmapped_base * 3.0, "MOCK-UNMAPPED"),
    ]:
        raw_quote = RawAirfareQuote(
            route_id=route.id,
            flight_number=flight,
            departure_datetime=datetime.combine(target_date + timedelta(days=7), datetime.min.time(), tzinfo=timezone.utc),
            advance_window_days=7,
            base_fare=0.0,
            taxes_fees=0.0,
            total_fare=fare,
            cabin_class="ECONOMY",
            collection_mode="MOCK",
            scraped_at=datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc),
        )
        db_session.add(raw_quote)
        db_session.commit()
        db_session.add(
            ProcessedAirfareQuote(
                raw_quote_id=raw_quote.id,
                route_id=route.id,
                advance_window_days=7,
                clean_total_fare=fare,
                is_outlier=False,
                processed_at=datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc),
            )
        )
    db_session.commit()

    route_indices = calculate_route_indices(db_session, target_date, collection_mode="MOCK")
    assert route_indices.loc[route_indices["route_key"] == "DEL-BOM", "dgca_weight"].iloc[0] == 1.0
    assert pd.isna(route_indices.loc[route_indices["route_key"] == "AAA-BBB", "dgca_weight"].iloc[0])

    index_res = calculate_composite_index(db_session, target_date, collection_mode="MOCK")
    assert index_res is not None
    assert index_res.index_value == 100.0


def test_index_uses_scraped_at_collection_date_not_processed_at(db_session):
    """Verify delayed processing after IST midnight does not move the observation date."""
    route = Route(origin_code="DEL", destination_code="BOM", dgca_weight=1.0, is_active=True)
    db_session.add(route)
    db_session.commit()

    collection_date = PROTOTYPE_REFERENCE_START_DATE
    raw_quote = None
    for window in (1, 7, 15, 30, 45):
        baseline = get_route_baseline_fare("DEL-BOM", window)
        raw_quote = RawAirfareQuote(
            route_id=route.id,
            flight_number=f"QP-MIDNIGHT-{window}",
            departure_datetime=datetime.combine(collection_date + timedelta(days=window), datetime.min.time(), tzinfo=timezone.utc),
            advance_window_days=window,
            base_fare=0.0,
            taxes_fees=0.0,
            total_fare=baseline,
            cabin_class="ECONOMY",
            collection_mode="LIVE",
            scraped_at=datetime(2026, 9, 5, 18, 20, tzinfo=timezone.utc),  # 23:50 IST on Sep 5
        )
        db_session.add(raw_quote)
        db_session.commit()
        db_session.add(
            ProcessedAirfareQuote(
                raw_quote_id=raw_quote.id,
                route_id=route.id,
                advance_window_days=window,
                clean_total_fare=baseline,
                is_outlier=False,
                processed_at=datetime(2026, 9, 5, 18, 50, tzinfo=timezone.utc),  # 00:20 IST on Sep 6
            )
        )
    db_session.commit()

    assert live_reference_status(db_session).is_available
    assert collection_date_from_timestamp(raw_quote.scraped_at) == collection_date
    assert not calculate_route_indices(db_session, collection_date, collection_mode="LIVE").empty
    assert calculate_route_indices(db_session, date(2026, 9, 6), collection_mode="LIVE").empty
