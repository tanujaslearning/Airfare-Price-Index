"""Database seeding script for initializing reference routes, carriers, and OTAs."""

import logging
from typing import Optional
from sqlalchemy.orm import Session
from backend.app.db.session import SessionLocal, init_db
from backend.app.data.route_basket import APPROVED_ROUTE_BASKET
from backend.app.models.route import Route
from backend.app.models.airline import Airline

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("apix.seed")

# 1. Key DGCA reference routes with realistic passenger share weights
INITIAL_ROUTES = [route.seed_dict() for route in APPROVED_ROUTE_BASKET]

# 2. Major Indian Scheduled Carriers and Online Travel Agencies (OTAs)
INITIAL_AIRLINES = [
    {"code": "6E", "name": "IndiGo Airlines", "is_ota": False},
    {"code": "AI", "name": "Air India", "is_ota": False},
    {"code": "SG", "name": "SpiceJet", "is_ota": False},
    {"code": "QP", "name": "Akasa Air", "is_ota": False},
    {"code": "MMT", "name": "MakeMyTrip", "is_ota": True},
    {"code": "EMT", "name": "EaseMyTrip", "is_ota": True},
]


def seed_routes(db: Session) -> int:
    """Seeds initial DGCA flight routes idempotently."""
    inserted = 0
    for r_data in INITIAL_ROUTES:
        existing = (
            db.query(Route)
            .filter(
                Route.origin_code == r_data["origin_code"],
                Route.destination_code == r_data["destination_code"],
            )
            .first()
        )
        if not existing:
            route = Route(**r_data)
            db.add(route)
            inserted += 1
            logger.info("Created Route: %s -> %s (weight: %.2f)", r_data["origin_code"], r_data["destination_code"], r_data["dgca_weight"])
        else:
            # Update weights/distances if changed
            existing.distance_km = r_data["distance_km"]
            existing.dgca_weight = r_data["dgca_weight"]
            existing.is_active = r_data["is_active"]
    db.commit()
    return inserted


def seed_airlines(db: Session) -> int:
    """Seeds major Indian airlines and OTAs idempotently."""
    inserted = 0
    for a_data in INITIAL_AIRLINES:
        existing = db.query(Airline).filter(Airline.code == a_data["code"]).first()
        if not existing:
            airline = Airline(**a_data)
            db.add(airline)
            inserted += 1
            logger.info("Created %s: %s (%s)", "OTA" if a_data["is_ota"] else "Airline", a_data["name"], a_data["code"])
        else:
            existing.name = a_data["name"]
            existing.is_ota = a_data["is_ota"]
    db.commit()
    return inserted


def seed_database(db: Optional[Session] = None) -> None:
    """Entrypoint to seed reference data into database."""
    # Ensure tables exist
    init_db()

    session_created = False
    if db is None:
        db = SessionLocal()
        session_created = True

    try:
        logger.info("--- Starting Database Seeding ---")
        routes_added = seed_routes(db)
        airlines_added = seed_airlines(db)
        logger.info("--- Seeding Complete: %d routes added, %d airlines/OTAs added ---", routes_added, airlines_added)
    except Exception as exc:
        db.rollback()
        logger.error("Database seeding failed: %s", exc)
        raise
    finally:
        if session_created:
            db.close()


if __name__ == "__main__":
    seed_database()
