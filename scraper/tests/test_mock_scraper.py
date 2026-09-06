"""Unit tests for MockFlightScraper and BaseFlightScraper capabilities."""

import pytest
from datetime import date, timedelta
from scraper.base.mock_scraper import MockFlightScraper, ADVANCE_WINDOWS
from scraper.base.base_scraper import (
    ScraperConfig,
    CaptchaDetectedException,
    ScrapingBlockedException,
    RouteUnavailableException,
    RobotsDisallowedException,
)
from backend.app.schemas.quote import RawAirfareQuoteCreate


@pytest.mark.asyncio
async def test_mock_scraper_deterministic_generation():
    """Verify mock scraper generates identical quotes with fixed seed."""
    scraper_a = MockFlightScraper(random_seed=100)
    scraper_b = MockFlightScraper(random_seed=100)

    target_date = date(2026, 9, 15)
    quotes_a = await scraper_a.fetch_quotes("DEL", "BOM", target_date)
    quotes_b = await scraper_b.fetch_quotes("DEL", "BOM", target_date)

    assert len(quotes_a) == len(quotes_b)
    for qa, qb in zip(quotes_a, quotes_b):
        assert qa.flight_number == qb.flight_number
        assert qa.total_fare == qb.total_fare
        assert qa.base_fare == qb.base_fare
        assert qa.taxes_fees == qb.taxes_fees
        assert isinstance(qa, RawAirfareQuoteCreate)


@pytest.mark.asyncio
async def test_mock_scraper_economic_curve():
    """Verify economic pricing curve: T+1 fares are significantly higher than T+45 fares."""
    scraper = MockFlightScraper(random_seed=42)
    today = date(2026, 9, 1)

    t1_date = today + timedelta(days=1)
    t45_date = today + timedelta(days=45)

    quotes_t1 = await scraper.fetch_quotes("DEL", "BLR", t1_date)
    quotes_t45 = await scraper.fetch_quotes("DEL", "BLR", t45_date)

    avg_t1 = sum(q.total_fare for q in quotes_t1) / len(quotes_t1)
    avg_t45 = sum(q.total_fare for q in quotes_t45) / len(quotes_t45)

    # T+1 average fare should be at least 1.4x higher than T+45
    assert avg_t1 > avg_t45
    assert avg_t1 >= avg_t45 * 1.30


@pytest.mark.asyncio
async def test_mock_scraper_complete_matrix():
    """Verify matrix generation across all 6 seed routes and 5 advance windows."""
    scraper = MockFlightScraper(random_seed=999)
    routes = [
        {"id": 1, "origin_code": "DEL", "destination_code": "BOM"},
        {"id": 2, "origin_code": "DEL", "destination_code": "BLR"},
        {"id": 3, "origin_code": "BOM", "destination_code": "BLR"},
        {"id": 4, "origin_code": "DEL", "destination_code": "CCU"},
        {"id": 5, "origin_code": "BLR", "destination_code": "HYD"},
        {"id": 6, "origin_code": "MAA", "destination_code": "DEL"},
    ]
    carrier_map = {"6E": 1, "AI": 2, "SG": 3, "QP": 4}

    collection_date = date(2026, 9, 1)
    matrix_quotes = await scraper.generate_complete_matrix(collection_date, routes, carrier_map)

    # 6 routes * 5 windows * (3 IndiGo + 2 Air India + 2 SpiceJet + 2 Akasa = 9 flights) = 270 quotes
    expected_count = len(routes) * len(ADVANCE_WINDOWS) * 9
    assert len(matrix_quotes) == expected_count

    # Check advance windows are all represented
    windows_found = set(q.advance_window_days for q in matrix_quotes)
    assert windows_found == set(ADVANCE_WINDOWS)


def test_base_scraper_block_and_captcha_detection():
    """Verify bot challenge and HTTP block signatures trigger correct exceptions."""
    scraper = MockFlightScraper()

    # Cloudflare challenge
    with pytest.raises(CaptchaDetectedException):
        scraper.detect_block_or_captcha("<html><body><div id='cf-challenge-running'>Checking browser</div></body></html>")

    # reCAPTCHA
    with pytest.raises(CaptchaDetectedException):
        scraper.detect_block_or_captcha("<html><div class='g-recaptcha'></div></html>")

    # Access Denied / 403 Forbidden
    with pytest.raises(ScrapingBlockedException):
        scraper.detect_block_or_captcha("<html><title>403 Forbidden</title><body>Access Denied</body></html>")


def test_scraper_exception_hierarchy():
    """Verify custom scraping exception classes."""
    assert issubclass(CaptchaDetectedException, ScrapingBlockedException)
    assert issubclass(RouteUnavailableException, Exception)
    assert issubclass(RobotsDisallowedException, Exception)
