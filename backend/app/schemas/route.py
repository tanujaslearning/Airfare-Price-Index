"""Pydantic schemas for Route entity."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class RouteBase(BaseModel):
    """Base route properties."""
    origin_code: str = Field(..., min_length=3, max_length=3, description="IATA 3-letter origin airport code")
    destination_code: str = Field(..., min_length=3, max_length=3, description="IATA 3-letter destination airport code")
    distance_km: Optional[float] = Field(None, ge=0.0, description="Great-circle distance in kilometers")
    dgca_weight: float = Field(0.0, ge=0.0, description="Weighted share in national passenger traffic")
    is_active: bool = Field(True, description="Whether route is active for scraping")


class RouteCreate(RouteBase):
    """Schema for creating a new route."""
    pass


class RouteUpdate(BaseModel):
    """Schema for updating an existing route."""
    distance_km: Optional[float] = Field(None, ge=0.0)
    dgca_weight: Optional[float] = Field(None, ge=0.0)
    is_active: Optional[bool] = None


class RouteRead(RouteBase):
    """Schema for returning route details."""
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
