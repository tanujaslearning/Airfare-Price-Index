"""Route database model."""

from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import Integer, String, Float, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.db.base_class import Base

if TYPE_CHECKING:
    from backend.app.models.quote import RawAirfareQuote, ProcessedAirfareQuote


class Route(Base):
    """Flight route entity representing origin-destination pairs."""

    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    origin_code: Mapped[str] = mapped_column(String(3), index=True, nullable=False, doc="IATA 3-letter origin airport code")
    destination_code: Mapped[str] = mapped_column(String(3), index=True, nullable=False, doc="IATA 3-letter destination airport code")
    distance_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True, doc="Great-circle distance in kilometers")
    dgca_weight: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, doc="Weighted share in national passenger traffic")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, doc="Active status for scraper inclusion")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    raw_quotes: Mapped[List["RawAirfareQuote"]] = relationship(
        "RawAirfareQuote",
        back_populates="route",
        cascade="all, delete-orphan",
    )
    processed_quotes: Mapped[List["ProcessedAirfareQuote"]] = relationship(
        "ProcessedAirfareQuote",
        back_populates="route",
        cascade="all, delete-orphan",
    )

    @property
    def route_key(self) -> str:
        """Returns standard route representation, e.g., 'DEL-BOM'."""
        return f"{self.origin_code}-{self.destination_code}"

    @property
    def route_code(self) -> str:
        """Alias for route_key, e.g. 'DEL-BOM'."""
        return self.route_key

    @property
    def origin(self) -> str:
        """Alias for origin_code."""
        return self.origin_code

    @property
    def destination(self) -> str:
        """Alias for destination_code."""
        return self.destination_code

    @property
    def distance(self) -> Optional[float]:
        """Alias for distance_km."""
        return self.distance_km

    @property
    def passenger_market_weight(self) -> float:
        """Alias for dgca_weight."""
        return self.dgca_weight

    def __repr__(self) -> str:
        return f"<Route(id={self.id}, route='{self.route_key}', weight={self.dgca_weight}, active={self.is_active})>"
