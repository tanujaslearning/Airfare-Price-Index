"""Unit tests for SQLAlchemy models, Pydantic schemas, and database seed logic."""

import pytest
from datetime import datetime, date, timezone
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base_class import Base
from backend.app.models.route import Route
from backend.app.models.airline import Airline
from backend.app.models.scraping_job import ScrapingJobLog
from backend.app.models.quote import RawAirfareQuote, ProcessedAirfareQuote
from backend.app.models.index_value import AirfareIndexValue
from backend.app.models.dgca_reference import DgcaReferenceData

from backend.app.schemas.route import RouteCreate, RouteRead
from backend.app.schemas.airline import AirlineCreate, AirlineRead
from backend.app.schemas.scraping_job import ScrapingJobLogCreate
from backend.app.schemas.quote import RawAirfareQuoteCreate, ProcessedAirfareQuoteCreate
from backend.app.schemas.index import AirfareIndexValueCreate
from backend.app.schemas.dgca import DgcaReferenceDataCreate

from backend.app.db.seed import seed_database


@pytest.fixture(scope="function")
def db_session():
    """In-memory SQLite session fixture for isolated model tests."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_route_model_and_relationships(db_session):
    """Test Route model creation and cascade relationship with quotes."""
    route = Route(
        origin_code="DEL",
        destination_code="BOM",
        distance_km=1148.0,
        dgca_weight=0.25,
        is_active=True,
    )
    db_session.add(route)
    db_session.commit()
    db_session.refresh(route)

    assert route.id is not None
    assert route.route_key == "DEL-BOM"
    assert route.dgca_weight == 0.25

    airline = Airline(code="6E", name="IndiGo", is_ota=False)
    db_session.add(airline)
    db_session.commit()
    db_session.refresh(airline)

    # Attach raw quote
    raw_quote = RawAirfareQuote(
        source_id=airline.id,
        route_id=route.id,
        flight_number="6E-101",
        departure_datetime=datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc),
        advance_window_days=7,
        base_fare=3500.0,
        taxes_fees=1000.0,
        total_fare=4500.0,
        cabin_class="ECONOMY",
    )
    db_session.add(raw_quote)
    db_session.commit()
    db_session.refresh(raw_quote)

    # Attach processed quote
    processed_quote = ProcessedAirfareQuote(
        raw_quote_id=raw_quote.id,
        route_id=route.id,
        advance_window_days=7,
        clean_total_fare=4500.0,
        is_outlier=False,
    )
    db_session.add(processed_quote)
    db_session.commit()

    assert len(route.raw_quotes) == 1
    assert len(route.processed_quotes) == 1
    assert route.raw_quotes[0].airline_source.name == "IndiGo"
    assert raw_quote.processed_quotes[0].clean_total_fare == 4500.0


def test_scraping_job_log_model(db_session):
    """Test ScrapingJobLog lifecycle."""
    job = ScrapingJobLog(
        source_name="IndiGo Direct",
        status="RUNNING",
        total_scraped=0,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    assert job.id is not None
    assert job.status == "RUNNING"
    assert job.start_time is not None

    job.status = "COMPLETED"
    job.total_scraped = 42
    job.end_time = datetime.now(timezone.utc)
    db_session.commit()
    db_session.refresh(job)

    assert job.status == "COMPLETED"
    assert job.total_scraped == 42


def test_airfare_index_value_model(db_session):
    """Test AirfareIndexValue record insertion."""
    idx = AirfareIndexValue(
        date=date(2026, 8, 31),
        frequency="daily",
        index_value=105.4,
        baseline_period="2026-Q1",
    )
    db_session.add(idx)
    db_session.commit()
    db_session.refresh(idx)

    assert idx.id is not None
    assert idx.frequency == "daily"
    assert idx.index_value == 105.4


def test_dgca_reference_data_model(db_session):
    """Test DgcaReferenceData insertion and querying."""
    ref = DgcaReferenceData(
        month=7,
        year=2026,
        origin_code="DEL",
        destination_code="BOM",
        avg_fare=5250.0,
        pax_count=185000,
    )
    db_session.add(ref)
    db_session.commit()
    db_session.refresh(ref)

    assert ref.id is not None
    assert ref.avg_fare == 5250.0
    assert ref.pax_count == 185000


def test_pydantic_schema_validations():
    """Verify Pydantic schemas enforce bounds and types."""
    # Route validation
    r = RouteCreate(origin_code="DEL", destination_code="BLR", distance_km=1740.0, dgca_weight=0.20)
    assert r.origin_code == "DEL"
    with pytest.raises(ValidationError):
        RouteCreate(origin_code="DELHI", destination_code="BLR")  # max 3 chars

    # Airline validation
    a = AirlineCreate(code="AI", name="Air India", is_ota=False)
    assert a.code == "AI"

    # Index frequency validation
    idx = AirfareIndexValueCreate(
        date=date(2026, 8, 31),
        frequency="daily",
        collection_mode="MOCK",
        index_value=102.5,
    )
    assert idx.frequency == "daily"
    assert idx.collection_mode == "MOCK"
    with pytest.raises(ValidationError):
        AirfareIndexValueCreate(
            date=date(2026, 8, 31),
            frequency="yearly",
            collection_mode="MOCK",
            index_value=100.0,
        )  # Invalid frequency

    # DGCA month validation
    d = DgcaReferenceDataCreate(month=12, year=2026, origin_code="DEL", destination_code="BOM", avg_fare=4500.0)
    assert d.month == 12
    with pytest.raises(ValidationError):
        DgcaReferenceDataCreate(month=13, year=2026, origin_code="DEL", destination_code="BOM", avg_fare=4500.0)


def test_database_seeding(db_session):
    """Verify seed_database populates routes, weights, and carriers."""
    seed_database(db=db_session)

    routes = db_session.query(Route).all()
    assert len(routes) == 6

    total_weight = sum(r.dgca_weight for r in routes)
    assert round(total_weight, 2) == 1.00

    airlines = db_session.query(Airline).all()
    assert len(airlines) == 6

    carriers = [a for a in airlines if not a.is_ota]
    otas = [a for a in airlines if a.is_ota]
    assert len(carriers) == 4  # IndiGo, Air India, SpiceJet, Akasa Air
    assert len(otas) == 2      # MakeMyTrip, EaseMyTrip
