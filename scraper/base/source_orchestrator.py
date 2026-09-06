"""Source orchestration, failover, and cooldown for live website collection."""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from backend.app.schemas.quote import RawAirfareQuoteCreate
from scraper.base.base_scraper import (
    BaseFlightScraper,
    CaptchaDetectedException,
    RobotsDisallowedException,
    RobotsInconclusiveException,
    RouteUnavailableException,
    ScrapingBlockedException,
    ScrapingException,
)

logger = logging.getLogger("apix.scraper.orchestrator")


AVAILABLE = "AVAILABLE"
SUCCESS = "SUCCESS"
TEMPORARILY_BLOCKED = "TEMPORARILY_BLOCKED"
CAPTCHA = "CAPTCHA"
RATE_LIMITED = "RATE_LIMITED"
ACCESS_DENIED = "ACCESS_DENIED"
ROBOTS_INCONCLUSIVE = "ROBOTS_INCONCLUSIVE"
ERROR = "ERROR"
NO_AVAILABILITY = "NO_AVAILABILITY"


@dataclass
class SourceHealth:
    """In-memory source state for a controlled collection process."""

    state: str = AVAILABLE
    cooldown_until: Optional[datetime] = None
    last_error: Optional[str] = None


@dataclass
class SourceAttempt:
    """A single source attempt outcome."""

    source_name: str
    state: str
    message: str
    quotes_count: int = 0


@dataclass
class SourceCollectionResult:
    """Structured result returned by the source orchestrator."""

    quotes: List[RawAirfareQuoteCreate] = field(default_factory=list)
    attempts: List[SourceAttempt] = field(default_factory=list)

    @property
    def succeeded_sources(self) -> List[str]:
        return [attempt.source_name for attempt in self.attempts if attempt.state == SUCCESS]

    @property
    def failed_sources(self) -> List[str]:
        return [attempt.source_name for attempt in self.attempts if attempt.state != SUCCESS]


class SourceOrchestrator:
    """Attempts ordered scraper sources with failover and deterministic cooldown."""

    def __init__(
        self,
        sources: List[BaseFlightScraper],
        cooldown_seconds: int = 900,
        source_id_by_name: Optional[Dict[str, Optional[int]]] = None,
    ):
        self.sources = sources
        self.cooldown_seconds = cooldown_seconds
        self.source_id_by_name = source_id_by_name or {}
        self.health: Dict[str, SourceHealth] = {
            source.config.source_name: SourceHealth()
            for source in sources
        }

    def is_source_available(self, source_name: str, now: Optional[datetime] = None) -> bool:
        health = self.health.get(source_name, SourceHealth())
        if health.cooldown_until is None:
            return True
        current = now or datetime.now(timezone.utc)
        if current >= health.cooldown_until:
            health.state = AVAILABLE
            health.cooldown_until = None
            health.last_error = None
            self.health[source_name] = health
            return True
        return False

    def mark_failure(self, source_name: str, state: str, message: str) -> None:
        self.health[source_name] = SourceHealth(
            state=state,
            cooldown_until=datetime.now(timezone.utc) + timedelta(seconds=self.cooldown_seconds),
            last_error=message,
        )

    def mark_success(self, source_name: str) -> None:
        self.health[source_name] = SourceHealth(state=SUCCESS)

    async def collect_quotes(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str,
        route_id: int,
        source_id: Optional[int],
        advance_window_days: Optional[int] = None,
    ) -> SourceCollectionResult:
        """Collect quotes from the first eligible successful source."""
        result = SourceCollectionResult()

        for source in self.sources:
            source_name = source.config.source_name
            if not self.is_source_available(source_name):
                message = f"{source_name} is in cooldown"
                result.attempts.append(SourceAttempt(source_name, TEMPORARILY_BLOCKED, message))
                continue

            try:
                attempt_source_id = self.source_id_by_name.get(source_name, source_id)
                quotes = await source.fetch_quotes(
                    origin=origin,
                    destination=destination,
                    departure_date=departure_date,
                    cabin_class=cabin_class,
                    route_id=route_id,
                    source_id=attempt_source_id,
                    advance_window_days=advance_window_days,
                )
            except Exception as exc:
                state = self.classify_exception(exc)
                message = str(exc)
                logger.warning("Source %s failed with state=%s: %s", source_name, state, message)
                self.mark_failure(source_name, state, message)
                result.attempts.append(SourceAttempt(source_name, state, message))
                continue

            self.mark_success(source_name)
            result.quotes.extend(quotes)
            result.attempts.append(SourceAttempt(source_name, SUCCESS, "success", len(quotes)))
            if quotes:
                break

        if not result.quotes and len(self.sources) == 1 and result.attempts:
            result.attempts.append(
                SourceAttempt(
                    "SourceOrchestrator",
                    ERROR,
                    f"{self.sources[0].config.source_name} unavailable; no live fallback source configured.",
                )
            )

        return result

    @staticmethod
    def classify_exception(exc: Exception) -> str:
        message = str(exc).lower()
        if isinstance(exc, CaptchaDetectedException):
            return CAPTCHA
        if isinstance(exc, RobotsDisallowedException):
            return ACCESS_DENIED
        if isinstance(exc, RobotsInconclusiveException):
            return ROBOTS_INCONCLUSIVE
        if isinstance(exc, ScrapingBlockedException):
            if "429" in message or "too many" in message or "rate" in message:
                return RATE_LIMITED
            if "403" in message or "access denied" in message or "forbid" in message:
                return ACCESS_DENIED
            return TEMPORARILY_BLOCKED
        if isinstance(exc, RouteUnavailableException):
            return NO_AVAILABILITY
        if isinstance(exc, (TimeoutError, ScrapingException)):
            return ERROR
        return ERROR
