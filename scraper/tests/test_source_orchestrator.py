"""Tests for live source failover and cooldown."""

from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

import pytest

from backend.app.schemas.quote import RawAirfareQuoteCreate
from scraper.base.base_scraper import (
    BaseFlightScraper,
    CaptchaDetectedException,
    RobotsInconclusiveException,
    RouteUnavailableException,
    ScraperConfig,
    ScrapingBlockedException,
)
from scraper.base.source_orchestrator import (
    ACCESS_DENIED,
    CAPTCHA,
    ERROR,
    NO_AVAILABILITY,
    RATE_LIMITED,
    ROBOTS_INCONCLUSIVE,
    SUCCESS,
    TEMPORARILY_BLOCKED,
    SourceOrchestrator,
)


def _quote() -> RawAirfareQuoteCreate:
    return RawAirfareQuoteCreate(
        source_id=2,
        route_id=1,
        flight_number="AI-101",
        departure_datetime=datetime(2026, 9, 11, tzinfo=timezone.utc),
        arrival_datetime=None,
        advance_window_days=7,
        base_fare=0.0,
        taxes_fees=0.0,
        total_fare=5500.0,
        cabin_class="ECONOMY",
        scraped_at=datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc),
    )


class FakeScraper(BaseFlightScraper):
    def __init__(self, source_name: str, quotes=None, exc: Optional[Exception] = None):
        super().__init__(ScraperConfig(source_name=source_name, base_url=f"https://{source_name}.example"))
        self.quotes = quotes or []
        self.exc = exc
        self.calls = 0

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
        self.calls += 1
        self.advance_window_days = advance_window_days
        if self.exc:
            raise self.exc
        return self.quotes


@pytest.mark.asyncio
async def test_orchestrator_collects_from_successful_source():
    scraper = FakeScraper("Air India", quotes=[_quote()])
    orchestrator = SourceOrchestrator([scraper])

    result = await orchestrator.collect_quotes("DEL", "BOM", date(2026, 9, 11), "ECONOMY", 1, 2, advance_window_days=7)

    assert len(result.quotes) == 1
    assert result.attempts[0].state == SUCCESS
    assert scraper.calls == 1
    assert scraper.advance_window_days == 7


@pytest.mark.asyncio
async def test_orchestrator_fails_over_after_captcha():
    blocked = FakeScraper("Air India", exc=CaptchaDetectedException("captcha"))
    fallback = FakeScraper("Fallback", quotes=[_quote()])
    orchestrator = SourceOrchestrator([blocked, fallback])

    result = await orchestrator.collect_quotes("DEL", "BOM", date(2026, 9, 11), "ECONOMY", 1, 2)

    assert [attempt.state for attempt in result.attempts] == [CAPTCHA, SUCCESS]
    assert len(result.quotes) == 1
    assert blocked.calls == 1
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_orchestrator_cooldown_skips_blocked_source():
    blocked = FakeScraper("Air India", exc=ScrapingBlockedException("HTTP 429"))
    fallback = FakeScraper("Fallback", quotes=[_quote()])
    orchestrator = SourceOrchestrator([blocked, fallback], cooldown_seconds=60)

    await orchestrator.collect_quotes("DEL", "BOM", date(2026, 9, 11), "ECONOMY", 1, 2)
    second = await orchestrator.collect_quotes("DEL", "BOM", date(2026, 9, 11), "ECONOMY", 1, 2)

    assert second.attempts[0].state == TEMPORARILY_BLOCKED
    assert blocked.calls == 1
    assert fallback.calls == 2


@pytest.mark.asyncio
async def test_orchestrator_reports_all_sources_unavailable():
    blocked = FakeScraper("Air India", exc=ScrapingBlockedException("HTTP 403"))
    orchestrator = SourceOrchestrator([blocked])

    result = await orchestrator.collect_quotes("DEL", "BOM", date(2026, 9, 11), "ECONOMY", 1, 2)

    assert result.quotes == []
    assert result.attempts[0].state == ACCESS_DENIED
    assert "no live fallback source configured" in result.attempts[-1].message


def test_orchestrator_classifies_429_and_generic_timeout():
    assert SourceOrchestrator.classify_exception(ScrapingBlockedException("HTTP 429")) == RATE_LIMITED
    assert SourceOrchestrator.classify_exception(TimeoutError("network timeout")) == ERROR
    assert SourceOrchestrator.classify_exception(RouteUnavailableException("No flights")) == NO_AVAILABILITY
    assert SourceOrchestrator.classify_exception(RobotsInconclusiveException("robots timeout")) == ROBOTS_INCONCLUSIVE


@pytest.mark.asyncio
async def test_orchestrator_uses_source_specific_ids_on_failover():
    blocked = FakeScraper("Akasa Air", exc=ScrapingBlockedException("HTTP 429"))
    fallback = FakeScraper("Air India", quotes=[_quote()])
    orchestrator = SourceOrchestrator(
        [blocked, fallback],
        source_id_by_name={"Akasa Air": 4, "Air India": 2},
    )

    result = await orchestrator.collect_quotes("DEL", "BOM", date(2026, 9, 11), "ECONOMY", 1, 4)

    assert [attempt.state for attempt in result.attempts] == [RATE_LIMITED, SUCCESS]
    assert result.quotes[0].source_id == 2
