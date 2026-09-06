"""Unit tests for Scraper base abstractions and data containers."""

import pytest
from datetime import date
from scraper.base.base_scraper import ScraperConfig, ScrapedQuote, ScrapingBlockedException


def test_scraped_quote_creation():
    """Verify ScrapedQuote data model instantiation."""
    quote = ScrapedQuote(
        source="DirectAirlines",
        airline="6E",
        flight_number="6E-101",
        origin="DEL",
        destination="BOM",
        departure_date=date(2026, 9, 15),
        departure_time="08:00",
        arrival_time="10:15",
        fare_amount=4500.0,
        currency="INR",
        cabin_class="ECONOMY",
    )
    assert quote.fare_amount == 4500.0
    assert quote.origin == "DEL"
    assert quote.destination == "BOM"
    assert quote.currency == "INR"


def test_scraper_config_defaults():
    """Verify default scraper configuration values."""
    config = ScraperConfig(source_name="TestSource", base_url="https://example.com")
    assert config.rate_limit_delay_seconds == 3.0
    assert config.respect_robots_txt is True
    assert "APIx-Research-Bot" in config.user_agent


def test_scraping_blocked_exception():
    """Verify exception hierarchy for blocked events."""
    with pytest.raises(ScrapingBlockedException):
        raise ScrapingBlockedException("Bot detection challenge triggered")
