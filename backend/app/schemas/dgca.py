"""Pydantic schemas for DGCA Reference Data."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class DgcaReferenceDataBase(BaseModel):
    """Base schema for DGCA monthly benchmark data."""
    month: int = Field(..., ge=1, le=12, description="Month (1-12)")
    year: int = Field(..., ge=2000, le=2100, description="Year (e.g. 2025, 2026)")
    origin_code: str = Field(..., min_length=3, max_length=3, description="Origin airport code")
    destination_code: str = Field(..., min_length=3, max_length=3, description="Destination airport code")
    avg_fare: float = Field(..., gt=0.0, description="Official average airfare")
    pax_count: int = Field(0, ge=0, description="Monthly passenger volume")


class DgcaReferenceDataCreate(DgcaReferenceDataBase):
    """Schema for inserting DGCA benchmark data."""
    pass


class DgcaReferenceDataRead(DgcaReferenceDataBase):
    """Schema for reading DGCA benchmark data."""
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
