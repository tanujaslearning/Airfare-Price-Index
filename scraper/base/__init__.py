"""Base scraper classes, interfaces, robots compliance, rate limiting, and mock generator."""

from scraper.base.robots_checker import RobotsChecker, RobotsDisallowedException
from scraper.base.rate_limiter import AsyncRateLimiter
from scraper.base.base_scraper import (
    BaseFlightScraper,
    ScraperConfig,
    ScrapedQuote,
    ScrapingException,
    ScrapingBlockedException,
    CaptchaDetectedException,
    RouteUnavailableException,
)
from scraper.base.mock_scraper import MockFlightScraper, ADVANCE_WINDOWS
from scraper.base.source_orchestrator import SourceOrchestrator, SourceCollectionResult, SourceAttempt, SourceHealth

__all__ = [
    "RobotsChecker",
    "RobotsDisallowedException",
    "AsyncRateLimiter",
    "BaseFlightScraper",
    "ScraperConfig",
    "ScrapedQuote",
    "ScrapingException",
    "ScrapingBlockedException",
    "CaptchaDetectedException",
    "RouteUnavailableException",
    "MockFlightScraper",
    "ADVANCE_WINDOWS",
    "SourceOrchestrator",
    "SourceCollectionResult",
    "SourceAttempt",
    "SourceHealth",
]
