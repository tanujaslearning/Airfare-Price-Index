"""Pydantic schemas package."""

from backend.app.schemas.health import HealthResponse
from backend.app.schemas.route import RouteBase, RouteCreate, RouteUpdate, RouteRead
from backend.app.schemas.airline import AirlineBase, AirlineCreate, AirlineUpdate, AirlineRead
from backend.app.schemas.scraping_job import ScrapingJobLogBase, ScrapingJobLogCreate, ScrapingJobLogUpdate, ScrapingJobLogRead
from backend.app.schemas.quote import (
    RawAirfareQuoteBase,
    RawAirfareQuoteCreate,
    RawAirfareQuoteRead,
    ProcessedAirfareQuoteBase,
    ProcessedAirfareQuoteCreate,
    ProcessedAirfareQuoteRead,
)
from backend.app.schemas.index import AirfareIndexValueBase, AirfareIndexValueCreate, AirfareIndexValueRead
from backend.app.schemas.dgca import DgcaReferenceDataBase, DgcaReferenceDataCreate, DgcaReferenceDataRead
from backend.app.schemas.api_responses import (
    IndexLatestResponse,
    IndexHistoricalResponse,
    RouteDetailResponse,
    RouteWindowBreakdown,
    RouteCorridorIndexResponse,
    PipelineTriggerRequest,
    PipelineTriggerResponse,
)

__all__ = [
    "HealthResponse",
    "RouteBase",
    "RouteCreate",
    "RouteUpdate",
    "RouteRead",
    "AirlineBase",
    "AirlineCreate",
    "AirlineUpdate",
    "AirlineRead",
    "ScrapingJobLogBase",
    "ScrapingJobLogCreate",
    "ScrapingJobLogUpdate",
    "ScrapingJobLogRead",
    "RawAirfareQuoteBase",
    "RawAirfareQuoteCreate",
    "RawAirfareQuoteRead",
    "ProcessedAirfareQuoteBase",
    "ProcessedAirfareQuoteCreate",
    "ProcessedAirfareQuoteRead",
    "AirfareIndexValueBase",
    "AirfareIndexValueCreate",
    "AirfareIndexValueRead",
    "DgcaReferenceDataBase",
    "DgcaReferenceDataCreate",
    "DgcaReferenceDataRead",
    "IndexLatestResponse",
    "IndexHistoricalResponse",
    "RouteDetailResponse",
    "RouteWindowBreakdown",
    "RouteCorridorIndexResponse",
    "PipelineTriggerRequest",
    "PipelineTriggerResponse",
]
