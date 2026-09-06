"""Airfare Price Index computed values model."""

from datetime import datetime, date, timezone
from typing import Optional
from sqlalchemy import Integer, String, Float, Date, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.db.base_class import Base


class AirfareIndexValue(Base):
    """Calculated Airfare Price Index metric over time."""

    __tablename__ = "airfare_index_values"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        doc="Target index evaluation date",
    )
    frequency: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        doc="Index interval granularity: 'daily', 'weekly', 'monthly'",
    )
    collection_mode: Mapped[str] = mapped_column(
        String(10),
        default="MOCK",
        nullable=False,
        index=True,
        doc="Observation provenance mode used for this persisted index: MOCK or LIVE",
    )
    index_value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Computed index score normalized to baseline (e.g. 100.0 base)",
    )
    baseline_period: Mapped[str] = mapped_column(
        String(50),
        default="2026-Q1",
        nullable=False,
        doc="Reference baseline description/period",
    )
    ma_7d: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="7-day rolling moving average",
    )
    ma_30d: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="30-day rolling moving average",
    )
    dod_change_pct: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Day-over-day percentage change in index",
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<AirfareIndexValue(id={self.id}, date={self.date}, freq='{self.frequency}', mode='{self.collection_mode}', value={self.index_value}, dod={self.dod_change_pct})>"
