"""DGCA benchmark reference dataset model."""

from datetime import datetime, timezone
from sqlalchemy import Integer, String, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.db.base_class import Base


class DgcaReferenceData(Base):
    """Directorate General of Civil Aviation (DGCA) official passenger & fare benchmarks."""

    __tablename__ = "dgca_reference_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True, doc="Month number (1-12)")
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True, doc="Year (e.g. 2025, 2026)")
    origin_code: Mapped[str] = mapped_column(String(3), nullable=False, index=True, doc="IATA 3-letter origin code")
    destination_code: Mapped[str] = mapped_column(String(3), nullable=False, index=True, doc="IATA 3-letter destination code")
    avg_fare: Mapped[float] = mapped_column(Float, nullable=False, doc="Official average route fare reported by DGCA")
    pax_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, doc="Monthly passenger volume on route")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<DgcaReferenceData(id={self.id}, route='{self.origin_code}-{self.destination_code}', {self.year}-{self.month:02d}, avg_fare={self.avg_fare})>"
