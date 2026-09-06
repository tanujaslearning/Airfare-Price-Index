"""Airline and OTA database model."""

from datetime import datetime, timezone
from typing import List, TYPE_CHECKING
from sqlalchemy import Integer, String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.db.base_class import Base

if TYPE_CHECKING:
    from backend.app.models.quote import RawAirfareQuote


class Airline(Base):
    """Airline carrier or Online Travel Agency (OTA) entity."""

    __tablename__ = "airlines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False, doc="IATA or custom identifier (e.g. 6E, AI, MMT)")
    name: Mapped[str] = mapped_column(String(100), nullable=False, doc="Full business or airline name")
    is_ota: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, doc="True if Online Travel Agency, False if direct airline carrier")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    raw_quotes: Mapped[List["RawAirfareQuote"]] = relationship(
        "RawAirfareQuote",
        back_populates="airline_source",
    )

    def __repr__(self) -> str:
        return f"<Airline(id={self.id}, code='{self.code}', name='{self.name}', is_ota={self.is_ota})>"
