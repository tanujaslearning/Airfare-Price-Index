"""SQLAlchemy ORM models package."""

from backend.app.models.route import Route
from backend.app.models.airline import Airline
from backend.app.models.scraping_job import ScrapingJobLog
from backend.app.models.quote import RawAirfareQuote, ProcessedAirfareQuote
from backend.app.models.index_value import AirfareIndexValue
from backend.app.models.dgca_reference import DgcaReferenceData

__all__ = [
    "Route",
    "Airline",
    "ScrapingJobLog",
    "RawAirfareQuote",
    "ProcessedAirfareQuote",
    "AirfareIndexValue",
    "DgcaReferenceData",
]
