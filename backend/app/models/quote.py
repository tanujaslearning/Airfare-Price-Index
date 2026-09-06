"""Airfare quote database models for raw and processed observation layers."""

from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.db.base_class import Base

if TYPE_CHECKING:
    from backend.app.models.route import Route
    from backend.app.models.airline import Airline
    from backend.app.models.scraping_job import ScrapingJobLog


class RawAirfareQuote(Base):
    """Raw collected quote from direct airline or OTA scraping source."""

    __tablename__ = "raw_airfare_quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    source_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("airlines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Reference to carrier or OTA",
    )
    route_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Origin-destination route",
    )
    flight_number: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True,
        index=True,
        doc="Flight number (e.g. 6E-204)",
    )
    departure_datetime: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        doc="Scheduled flight departure time",
    )
    arrival_datetime: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Scheduled flight arrival time",
    )
    advance_window_days: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        index=True,
        doc="Days between scrape collection date and flight departure date",
    )
    base_fare: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, doc="Airline base fare")
    taxes_fees: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, doc="Taxes, user development fees, fuel surcharge")
    total_fare: Mapped[float] = mapped_column(Float, nullable=False, index=True, doc="Total passenger payable fare")
    cabin_class: Mapped[str] = mapped_column(String(30), default="ECONOMY", nullable=False, doc="Cabin class: ECONOMY, BUSINESS, etc.")
    collection_mode: Mapped[str] = mapped_column(
        String(10),
        default="MOCK",
        nullable=False,
        index=True,
        doc="Observation provenance mode: MOCK or LIVE",
    )
    scraping_job_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("scraping_job_logs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Scraping job/run that created this quote, when known",
    )
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Relationships
    route: Mapped["Route"] = relationship("Route", back_populates="raw_quotes")
    airline_source: Mapped[Optional["Airline"]] = relationship("Airline", back_populates="raw_quotes")
    scraping_job: Mapped[Optional["ScrapingJobLog"]] = relationship("ScrapingJobLog", back_populates="raw_quotes")
    processed_quotes: Mapped[List["ProcessedAirfareQuote"]] = relationship(
        "ProcessedAirfareQuote",
        back_populates="raw_quote",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<RawAirfareQuote(id={self.id}, route_id={self.route_id}, fare={self.total_fare}, adv_days={self.advance_window_days})>"


class ProcessedAirfareQuote(Base):
    """Cleaned, validated, and outlier-flagged observation used for index calculation."""

    __tablename__ = "processed_airfare_quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    raw_quote_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("raw_airfare_quotes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Source raw quote reference",
    )
    route_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Origin-destination route",
    )
    advance_window_days: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        index=True,
        doc="Standardized advance purchase window in days (e.g. 1, 7, 15, 30)",
    )
    clean_total_fare: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        index=True,
        doc="Validated fare amount after sanity and currency checks",
    )
    is_outlier: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        doc="True if flagged by statistical anomaly detection",
    )
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Relationships
    raw_quote: Mapped[Optional["RawAirfareQuote"]] = relationship("RawAirfareQuote", back_populates="processed_quotes")
    route: Mapped["Route"] = relationship("Route", back_populates="processed_quotes")

    def __repr__(self) -> str:
        return f"<ProcessedAirfareQuote(id={self.id}, route_id={self.route_id}, clean_fare={self.clean_total_fare}, outlier={self.is_outlier})>"
