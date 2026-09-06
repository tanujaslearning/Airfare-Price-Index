"""Pydantic schemas for provenance and live-only reporting endpoints."""

from datetime import date as dt_date, datetime as dt_datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


CollectionMode = Literal["MOCK", "LIVE"]


class ProvenanceSummaryItem(BaseModel):
    """Raw quote count grouped by collection mode, provider/source, and job."""

    collection_mode: CollectionMode
    source: str
    job_id: Optional[int] = None
    quote_count: int = Field(..., ge=0)


class ProvenanceSummaryResponse(BaseModel):
    """Grouped raw quote provenance summary."""

    data: List[ProvenanceSummaryItem] = Field(default_factory=list)


class LiveSummaryItem(BaseModel):
    """Aggregated live-only fare summary for a route/source/window/date group."""

    route: str
    source: str
    advance_window_days: int = Field(..., ge=0)
    collection_date: dt_date
    quote_count: int = Field(..., ge=0)
    mean_fare: float
    min_fare: float
    max_fare: float


class LiveSummaryResponse(BaseModel):
    """Live-only aggregate response."""

    data: List[LiveSummaryItem] = Field(default_factory=list)


class ProvenanceJobItem(BaseModel):
    """Collection job with inferred mode and persisted quote count."""

    job_id: int
    source: str
    collection_mode: CollectionMode
    status: str
    collection_date: Optional[dt_date] = None
    quote_count: int = Field(..., ge=0)
    started_at: Optional[dt_datetime] = None
    completed_at: Optional[dt_datetime] = None


class ProvenanceJobsResponse(BaseModel):
    """Collection job provenance response."""

    data: List[ProvenanceJobItem] = Field(default_factory=list)


class LiveQuoteItem(BaseModel):
    """Single live raw quote with route/source provenance."""

    quote_id: int
    route: str
    source: str
    flight_number: Optional[str] = None
    departure_datetime: dt_datetime
    arrival_datetime: Optional[dt_datetime] = None
    advance_window_days: int = Field(..., ge=0)
    base_fare: float
    taxes_fees: float
    total_fare: float
    cabin_class: str
    scraped_at: dt_datetime
    scraping_job_id: Optional[int] = None


class LiveQuotesResponse(BaseModel):
    """Paginated live-only raw quote response."""

    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)
    data: List[LiveQuoteItem] = Field(default_factory=list)
