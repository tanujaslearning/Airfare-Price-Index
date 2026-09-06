"""Pydantic response models for API v1 REST endpoints."""

from datetime import date as dt_date, datetime as dt_datetime
from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from backend.app.schemas.index import AirfareIndexValueRead, CollectionMode


class IndexLatestResponse(BaseModel):
    """Latest computed National Composite Airfare Price Index."""
    date: dt_date = Field(..., description="Date of latest index score")
    frequency: str = Field("daily", description="Index calculation interval")
    collection_mode: CollectionMode = Field(..., description="Observation provenance mode used for calculation")
    index_value: float = Field(..., description="APIx Composite Index score (100.0 baseline)")
    baseline_period: str = Field("2026-Q1", description="Baseline period label")
    ma_7d: Optional[float] = Field(None, description="7-day rolling moving average")
    ma_30d: Optional[float] = Field(None, description="30-day rolling moving average")
    dod_change_pct: Optional[float] = Field(None, description="Day-over-day percentage change")
    calculated_at: dt_datetime = Field(..., description="Calculation timestamp in UTC")

    model_config = ConfigDict(from_attributes=True)


class IndexHistoricalResponse(BaseModel):
    """Historical time-series list of APIx index records."""
    count: int = Field(..., description="Total records returned")
    frequency: str = Field("daily", description="Time interval")
    collection_mode: CollectionMode = Field(..., description="Observation provenance mode filter")
    start_date: Optional[dt_date] = None
    end_date: Optional[dt_date] = None
    items: List[AirfareIndexValueRead] = Field(default_factory=list)


class FilterOption(BaseModel):
    """Dashboard filter option derived from persisted configuration or observations."""
    value: str
    label: str
    quote_count: int = Field(0, ge=0)


class FilterOptionsResponse(BaseModel):
    """Available dashboard filters for a selected collection mode."""
    collection_mode: CollectionMode
    origins: List[FilterOption] = Field(default_factory=list)
    destinations: List[FilterOption] = Field(default_factory=list)
    airlines: List[FilterOption] = Field(default_factory=list)
    periods: List[FilterOption] = Field(default_factory=list)


class RouteDetailResponse(BaseModel):
    """DGCA monitored route item."""
    id: int
    route_key: str
    route_code: str
    origin_code: str
    destination_code: str
    origin: str
    destination: str
    distance_km: Optional[float] = None
    distance: Optional[float] = None
    dgca_weight: Optional[float] = None
    passenger_market_weight: Optional[float] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


RouteWeightStatus = Literal["AVAILABLE", "MISSING", "NOT_MAPPED"]


class RouteWeightItemResponse(BaseModel):
    """DGCA passenger-traffic weight for one route."""

    route_code: str
    origin: str
    destination: str
    dgca_route_identifier: Optional[str] = None
    passenger_traffic: Optional[int] = None
    traffic_period: Optional[str] = None
    source: str
    source_reference: Optional[str] = None
    directionality: Optional[Literal["directional", "combined city-pair"]] = None
    status: RouteWeightStatus
    weight: Optional[float] = None


class RouteWeightCoverageResponse(BaseModel):
    """DGCA weight coverage summary."""

    available: int
    total: int
    percentage: float


class RouteWeightsResponse(BaseModel):
    """DGCA passenger-traffic route weighting response."""

    source: str
    traffic_period: Optional[str] = None
    directionality: Optional[str] = None
    routes: List[RouteWeightItemResponse] = Field(default_factory=list)
    coverage: RouteWeightCoverageResponse
    missing_routes: List[str] = Field(default_factory=list)
    unmapped_routes: List[str] = Field(default_factory=list)
    total_passenger_traffic: int = 0


class RouteWindowBreakdown(BaseModel):
    """Route metrics broken down by advance purchase window."""
    advance_window_days: int
    window_label: str = ""
    mean_fare: float
    baseline_fare: Optional[float] = None
    sub_index: Optional[float] = None
    quotes_count: int


class RouteCorridorIndexResponse(BaseModel):
    """Route-specific index scores and advance window pricing curves."""
    route_key: str
    route_code: str
    origin_code: str
    destination_code: str
    origin: Optional[str] = None
    destination: Optional[str] = None
    distance_km: Optional[float] = None
    distance: Optional[float] = None
    dgca_weight: Optional[float] = None
    passenger_market_weight: Optional[float] = None
    collection_mode: CollectionMode
    target_date: dt_date
    route_index: Optional[float] = None
    windows: List[RouteWindowBreakdown] = Field(default_factory=list)
    historical_points: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PipelineTriggerRequest(BaseModel):
    """Options for on-demand data pipeline execution."""
    collection_date: Optional[dt_date] = None
    random_seed: Optional[int] = 42
    force_recalculate: bool = True


class PipelineTriggerResponse(BaseModel):
    """Execution summary for an on-demand scraping and index calculation run."""
    status: str
    job_id: int
    source: str
    collection_date: dt_date
    ingested_count: int
    processed_quotes_count: int
    outliers_count: int
    clean_usable_count: int
    index_value: Optional[float] = None
    ma_7d: Optional[float] = None
    dod_change_pct: Optional[float] = None
    collection_mode: Optional[CollectionMode] = None
    timestamp: str
