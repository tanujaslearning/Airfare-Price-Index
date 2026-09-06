"""Pydantic schemas for Scraping Job logs."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ScrapingJobLogBase(BaseModel):
    """Base properties for scraping job log."""
    source_name: str = Field(..., max_length=100, description="Target scraper source name")
    status: str = Field("PENDING", description="Status: PENDING, RUNNING, COMPLETED, FAILED, BLOCKED")
    total_scraped: int = Field(0, ge=0, description="Number of scraped quotes")
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_log: Optional[str] = None


class ScrapingJobLogCreate(BaseModel):
    """Schema for creating a scraping job log."""
    source_name: str = Field(..., max_length=100)
    status: str = Field("RUNNING")
    start_time: Optional[datetime] = None


class ScrapingJobLogUpdate(BaseModel):
    """Schema for updating an existing scraping job log."""
    status: Optional[str] = None
    total_scraped: Optional[int] = Field(None, ge=0)
    end_time: Optional[datetime] = None
    error_log: Optional[str] = None


class ScrapingJobLogRead(ScrapingJobLogBase):
    """Schema for reading scraping job log details."""
    id: int
    start_time: datetime

    model_config = ConfigDict(from_attributes=True)
