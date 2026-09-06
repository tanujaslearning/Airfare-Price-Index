"""Pydantic schemas for Airfare Price Index values."""

from datetime import date as dt_date, datetime as dt_datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

CollectionMode = Literal["LIVE", "MOCK"]


class AirfareIndexValueBase(BaseModel):
    """Base schema for Airfare Price Index records."""
    date: dt_date = Field(..., description="Index calculation date")
    frequency: Literal["daily", "weekly", "monthly"] = Field(..., description="Aggregation frequency")
    collection_mode: CollectionMode = Field(..., description="Observation provenance mode used for calculation")
    index_value: float = Field(..., ge=0.0, description="Computed index numerical score")
    baseline_period: str = Field("2026-Q1", max_length=50, description="Baseline reference period")
    ma_7d: Optional[float] = Field(None, description="7-day rolling moving average")
    ma_30d: Optional[float] = Field(None, description="30-day rolling moving average")
    dod_change_pct: Optional[float] = Field(None, description="Day-over-day percentage change")


class AirfareIndexValueCreate(AirfareIndexValueBase):
    """Schema for creating a new index calculation value."""
    pass


class AirfareIndexValueRead(AirfareIndexValueBase):
    """Schema for reading index calculation values."""
    id: int
    calculated_at: dt_datetime

    model_config = ConfigDict(from_attributes=True)


class LiveIndexCoverage(BaseModel):
    """Coverage metrics for non-persisted live-only index analysis."""

    expected_route_window_combinations: int = Field(..., ge=0)
    observed_route_window_combinations: int = Field(..., ge=0)
    coverage_pct: float = Field(..., ge=0.0)
    minimum_required_coverage_pct: float = Field(..., ge=0.0)
    is_sufficient: bool


class LiveIndexWindowValue(BaseModel):
    """Live-only route/window sub-index detail."""

    route: str
    advance_window_days: int = Field(..., ge=0)
    quote_count: int = Field(..., ge=0)
    mean_fare: float
    baseline_fare: Optional[float] = None
    sub_index: Optional[float] = None
    sources_used: List[str] = Field(default_factory=list)


class LiveIndexRouteValue(BaseModel):
    """Live-only route index assembled from observed window values."""

    route: str
    route_index: Optional[float] = None
    dgca_weight: Optional[float] = None
    quote_count: int = Field(..., ge=0)
    windows_observed: int = Field(..., ge=0)
    window_values: List[LiveIndexWindowValue] = Field(default_factory=list)


class LiveIndexResponse(BaseModel):
    """Ad-hoc live-only index analysis response; it is not persisted."""

    status: Literal["SUFFICIENT_COVERAGE", "INSUFFICIENT_COVERAGE"]
    collection_mode: Literal["LIVE"] = "LIVE"
    collection_date: Optional[dt_date] = None
    index_value: Optional[float] = None
    index_scope: str = "NATIONAL"
    coverage: LiveIndexCoverage
    live_quote_count: int = Field(..., ge=0)
    routes_represented: int = Field(..., ge=0)
    advance_windows_represented: int = Field(..., ge=0)
    sources_represented: List[str] = Field(default_factory=list)
    route_values: List[LiveIndexRouteValue] = Field(default_factory=list)
    reference_status: str = "UNKNOWN"
    reference_period: Optional[str] = None
    reference_message: Optional[str] = None
