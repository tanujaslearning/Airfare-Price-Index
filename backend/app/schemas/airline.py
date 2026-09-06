"""Pydantic schemas for Airline and OTA entities."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class AirlineBase(BaseModel):
    """Base airline/OTA properties."""
    code: str = Field(..., min_length=2, max_length=10, description="Carrier/OTA code (e.g. 6E, AI, MMT)")
    name: str = Field(..., min_length=2, max_length=100, description="Carrier/OTA full name")
    is_ota: bool = Field(False, description="True if Online Travel Agency, False if direct airline")


class AirlineCreate(AirlineBase):
    """Schema for creating a new airline/OTA."""
    pass


class AirlineUpdate(BaseModel):
    """Schema for updating airline/OTA information."""
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    is_ota: Optional[bool] = None


class AirlineRead(AirlineBase):
    """Schema for reading airline/OTA information."""
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
