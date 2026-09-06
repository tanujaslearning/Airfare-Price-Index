"""Database session and engine management with dynamic PostgreSQL / SQLite fallback."""

from typing import Generator
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session
from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.db.base_class import Base

# Import all models to ensure they are registered with Base.metadata
import backend.app.models  # noqa: F401


def create_db_engine(db_url: str) -> Engine:
    """Creates SQLAlchemy engine with dialect-specific options."""
    if db_url.startswith("sqlite"):
        return create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            echo=False,
        )
    return create_engine(
        db_url,
        pool_pre_ping=True,
        echo=False,
    )


# Active database URL
db_url = settings.DATABASE_URL or "sqlite:///./apix.db"
logger.info("Initializing database connection with target: %s", db_url.split("@")[-1] if "@" in db_url else db_url)

try:
    engine = create_db_engine(db_url)
except Exception as err:
    logger.warning("Failed to initialize target engine (%s): %s. Falling back to local SQLite.", db_url, err)
    engine = create_db_engine("sqlite:///./apix.db")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db(target_engine: Engine = engine) -> None:
    """Initializes all database tables registered on declarative Base."""
    logger.info("Ensuring database tables are initialized...")
    Base.metadata.create_all(bind=target_engine)
    logger.info("Database tables initialized successfully.")


def get_db() -> Generator[Session, None, None]:
    """Dependency that yields a database session for a request and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    except Exception as exc:
        logger.error("Database session error: %s", exc)
        db.rollback()
        raise
    finally:
        db.close()
