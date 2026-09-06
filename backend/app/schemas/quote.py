"""Pydantic schemas for Raw and Processed Airfare Quotes."""

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class RawAirfareQuoteBase(BaseModel):
    """Base schema for raw airfare quotes."""
    source_id: Optional[int] = Field(None, description="Airline/OTA foreign key ID")
    route_id: int = Field(..., description="Route foreign key ID")
    flight_number: Optional[str] = Field(None, max_length=30)
    departure_datetime: datetime = Field(..., description="Departure timestamp")
    arrival_datetime: Optional[datetime] = None
    advance_window_days: int = Field(0, ge=0, description="Advance booking window in days")
    base_fare: float = Field(0.0, ge=0.0)
    taxes_fees: float = Field(0.0, ge=0.0)
    total_fare: float = Field(..., gt=0.0, description="Total fare amount")
    cabin_class: str = Field("ECONOMY", max_length=30)
    collection_mode: Optional[Literal["MOCK", "LIVE"]] = Field(
        None,
        description="Observation provenance mode stamped at ingestion",
    )
    scraping_job_id: Optional[int] = Field(None, description="Scraping job/run foreign key")
    scraped_at: Optional[datetime] = None


class RawAirfareQuoteCreate(RawAirfareQuoteBase):
    """Schema for creating a raw airfare quote."""
    pass


class RawAirfareQuoteRead(RawAirfareQuoteBase):
    """Schema for reading raw airfare quote details."""
    id: int
    scraped_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProcessedAirfareQuoteBase(BaseModel):
    """Base schema for normalized/cleaned quotes."""
    raw_quote_id: Optional[int] = None
    route_id: int
    advance_window_days: int = Field(0, ge=0)
    clean_total_fare: float = Field(..., gt=0.0)
    is_outlier: bool = False


class ProcessedAirfareQuoteCreate(ProcessedAirfareQuoteBase):
    """Schema for creating a processed airfare quote."""
    pass


class ProcessedAirfareQuoteRead(ProcessedAirfareQuoteBase):
    """Schema for reading processed airfare quote details."""
    id: int
    processed_at: datetime

    model_config = ConfigDict(from_attributes=True)
