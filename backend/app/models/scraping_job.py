"""Scraping job execution log model."""

from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.db.base_class import Base

if TYPE_CHECKING:
    from backend.app.models.quote import RawAirfareQuote


class ScrapingJobLog(Base):
    """Execution audit log for scraper runs and scheduled jobs."""

    __tablename__ = "scraping_job_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False, doc="Target airline/OTA name")
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False, index=True, doc="Status: PENDING, RUNNING, COMPLETED, FAILED, BLOCKED")
    total_scraped: Mapped[int] = mapped_column(Integer, default=0, nullable=False, doc="Number of quotes collected")
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    end_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_log: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Detailed error or block message if encountered",
    )
    raw_quotes: Mapped[List["RawAirfareQuote"]] = relationship(
        "RawAirfareQuote",
        back_populates="scraping_job",
    )

    def __repr__(self) -> str:
        return f"<ScrapingJobLog(id={self.id}, source='{self.source_name}', status='{self.status}', count={self.total_scraped})>"
