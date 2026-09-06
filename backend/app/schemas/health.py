"""Health check response schema."""

from typing import Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Schema for service health check response."""

    status: str = Field(default="healthy", description="Current service health status")
    app: str = Field(default="Airfare Price Index (APIx)", description="Application name")
    version: str = Field(default="0.1.0", description="Application version")
    environment: str = Field(default="development", description="Current running environment")
    database: Optional[str] = Field(
        default="not_checked",
        description="Database connectivity status (e.g. connected, disconnected, not_checked)",
    )
