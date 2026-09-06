"""Base Flight Scraper abstraction providing modularity, Playwright lifecycle, rate limiting, and block handling."""

import abc
import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

from backend.app.schemas.quote import RawAirfareQuoteCreate
from scraper.base.robots_checker import RobotsChecker, RobotsDisallowedException, RobotsInconclusiveException
from scraper.base.rate_limiter import AsyncRateLimiter

logger = logging.getLogger("apix.scraper.base")


# ============================================================================
# Standardized Error Classification Hierarchy
# ============================================================================

class ScrapingException(Exception):
    """Base exception for all airfare scraping failures."""
    pass


class ScrapingBlockedException(ScrapingException):
    """Raised when an anti-bot system, IP block (403/429), or WAF challenge is encountered."""
    pass


class CaptchaDetectedException(ScrapingBlockedException):
    """Raised when an explicit CAPTCHA (Cloudflare Turnstile, reCAPTCHA, hCaptcha, etc.) is detected.
    
    Per ethical guidelines, APIx will NEVER attempt to solve or bypass CAPTCHAs.
    """
    pass


class RouteUnavailableException(ScrapingException):
    """Raised when a valid carrier or OTA serves no available flights for the requested route/date."""
    pass


# Re-export RobotsDisallowedException
__all__ = [
    "ScrapingException",
    "ScrapingBlockedException",
    "CaptchaDetectedException",
    "RouteUnavailableException",
    "RobotsDisallowedException",
    "RobotsInconclusiveException",
    "ScraperConfig",
    "ScrapedQuote",
    "resolve_advance_window_days",
    "BaseFlightScraper",
]


@dataclass
class ScraperConfig:
    """Configuration container for web scrapers."""
    source_name: str
    base_url: str
    rate_limit_delay_seconds: float = 3.0
    timeout_seconds: float = 30.0
    respect_robots_txt: bool = True
    user_agent: str = "APIx-Research-Bot/0.1 (Academic Airfare Index Prototype; Contact: research@example.edu)"
    headless: bool = True
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class ScrapedQuote:
    """Normalized container for raw scraped airfare quote data."""
    source: str
    airline: str
    flight_number: Optional[str]
    origin: str
    destination: str
    departure_date: date
    departure_time: Optional[str]
    arrival_time: Optional[str]
    fare_amount: float
    currency: str
    cabin_class: str
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_payload: Optional[Dict[str, Any]] = None


def resolve_advance_window_days(
    departure_date: date,
    collected_at: datetime,
    requested_advance_window_days: Optional[int] = None,
) -> int:
    """Resolve the collection window, preferring explicit collection context."""
    if requested_advance_window_days is not None:
        if requested_advance_window_days < 0:
            raise ValueError("requested_advance_window_days must be non-negative")
        return int(requested_advance_window_days)
    return max(0, (departure_date - collected_at.date()).days)


class BaseFlightScraper(abc.ABC):
    """Abstract Base Class for all modular Airline and OTA scrapers.
    
    Manages Playwright browser lifecycles, rate limiting, robots.txt checks,
    and anti-bot block detection.
    """

    def __init__(
        self,
        config: ScraperConfig,
        robots_checker: Optional[RobotsChecker] = None,
        rate_limiter: Optional[AsyncRateLimiter] = None,
    ):
        self.config = config
        self.robots_checker = robots_checker or RobotsChecker(default_user_agent=config.user_agent)
        self.rate_limiter = rate_limiter or AsyncRateLimiter(default_delay_seconds=config.rate_limit_delay_seconds)
        self.rate_limiter.set_domain_delay(config.base_url, config.rate_limit_delay_seconds)

    async def verify_policy_and_rate_limit(self, target_url: str) -> None:
        """Verifies robots.txt permission and enforces rate limit delay before request."""
        if self.config.respect_robots_txt:
            allowed = await self.robots_checker.is_allowed(target_url, self.config.user_agent)
            if not allowed:
                logger.warning("Target URL %s is disallowed by robots.txt policy", target_url)
                raise RobotsDisallowedException(f"Robots.txt forbids scraping path: {target_url}")

            # Check if domain specifies crawl-delay
            crawl_delay = await self.robots_checker.get_crawl_delay(target_url, self.config.user_agent)
            if crawl_delay:
                await self.rate_limiter.wait(target_url, override_delay=crawl_delay)
                return

        # Standard rate limit
        await self.rate_limiter.wait(target_url)

    def detect_block_or_captcha(self, page_content: str, page_title: str = "") -> None:
        """Inspects HTML and title for bot challenges, raising structured exceptions."""
        content_lower = page_content.lower()
        title_lower = page_title.lower()

        # Check for CAPTCHA challenges
        captcha_signatures = [
            "captcha",
            "cf-challenge-running",
            "challenge-platform",
            "hcaptcha",
            "recaptcha",
            "turnstile",
            "perimeterx",
            "px-captcha",
            "please verify you are a human",
        ]
        for sig in captcha_signatures:
            if sig in content_lower or sig in title_lower:
                logger.warning("CAPTCHA / Bot challenge detected (%s) on %s", sig, self.config.source_name)
                raise CaptchaDetectedException(f"CAPTCHA signature '{sig}' encountered on {self.config.source_name}")

        # Check for HTTP blocks / Access Denied
        block_signatures = [
            "access denied",
            "403 forbidden",
            "error 1015",
            "error 1020",
            "rate limit exceeded",
            "too many requests",
            "blocked by cloudflare",
        ]
        for sig in block_signatures:
            if sig in content_lower or sig in title_lower:
                logger.warning("Access Block detected (%s) on %s", sig, self.config.source_name)
                raise ScrapingBlockedException(f"Scraping blocked: '{sig}' on {self.config.source_name}")

    async def create_browser_context(self, playwright):
        """Creates standard Playwright browser context with academic bot headers."""
        browser = await playwright.chromium.launch(
            headless=self.config.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=self.config.user_agent,
            viewport={"width": 1280, "height": 800},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers=self.config.headers,
        )
        return browser, context

    @abc.abstractmethod
    async def fetch_quotes(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str = "ECONOMY",
        route_id: int = 1,
        source_id: Optional[int] = None,
        advance_window_days: Optional[int] = None,
    ) -> List[RawAirfareQuoteCreate]:
        """Fetches airfare quotes for given route and date.
        
        Returns a list of RawAirfareQuoteCreate schemas ready for database ingestion.
        """
        raise NotImplementedError("Subclasses must implement fetch_quotes")
