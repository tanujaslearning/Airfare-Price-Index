"""Tests for Air India visible-fare parsing without live website access."""

from datetime import date, datetime, timezone

from scraper.airlines.air_india_scraper import AirIndiaWebsiteScraper


def _collect(html: str):
    return AirIndiaWebsiteScraper.extract_quotes_from_html(
        html,
        origin="DEL",
        destination="BOM",
        departure_date=date(2026, 9, 11),
        route_id=1,
        source_id=2,
        cabin_class="ECONOMY",
        collected_at=datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc),
    )


SINGLE_FARE_HTML = """
<section>
  <div>Delhi to</div><div>Mumbai</div>
  <div>Fri, Sep 11, 26</div>
  <div>Economy From</div><div>INR 6,823*</div>
  <div>One Way</div>
</section>
"""


def test_air_india_extracts_single_visible_fare_card():
    quotes = _collect(SINGLE_FARE_HTML)

    assert len(quotes) == 1
    assert quotes[0].source_id == 2
    assert quotes[0].route_id == 1
    assert quotes[0].flight_number is None
    assert quotes[0].departure_datetime.date() == date(2026, 9, 11)
    assert quotes[0].advance_window_days == 7
    assert quotes[0].base_fare == 0.0
    assert quotes[0].taxes_fees == 0.0
    assert quotes[0].total_fare == 6823.0
    assert quotes[0].cabin_class == "ECONOMY"


def test_air_india_uses_requested_advance_window_context():
    quotes = AirIndiaWebsiteScraper.extract_quotes_from_html(
        SINGLE_FARE_HTML,
        origin="DEL",
        destination="BOM",
        departure_date=date(2026, 9, 11),
        route_id=1,
        source_id=2,
        cabin_class="ECONOMY",
        collected_at=datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc),
        requested_advance_window_days=7,
    )

    assert quotes[0].advance_window_days == 7


def test_air_india_extracts_multiple_matching_results():
    html = """
    <div>Delhi to</div><div>Mumbai</div><div>Fri, Sep 11, 26</div><div>INR 6,823*</div>
    <div>Delhi to</div><div>Mumbai</div><div>Fri, Sep 11, 26</div><div>INR 7,100*</div>
    <div>Delhi to</div><div>Bengaluru</div><div>Fri, Sep 11, 26</div><div>INR 9,276*</div>
    """

    quotes = _collect(html)

    assert [q.total_fare for q in quotes] == [6823.0, 7100.0]


def test_air_india_extracts_base_and_tax_when_visible():
    html = """
    <div>DEL to BOM</div>
    <div>Fri, Sep 11, 2026</div>
    <div>Flight AI 2420</div>
    <div>Base Fare INR 4,000</div>
    <div>Taxes and Fees INR 1,150</div>
    <div>Total INR 5,150</div>
    """

    quotes = _collect(html)

    assert len(quotes) == 1
    assert quotes[0].flight_number == "AI-2420"
    assert quotes[0].base_fare == 4000.0
    assert quotes[0].taxes_fees == 1150.0
    assert quotes[0].total_fare == 5150.0


def test_air_india_ignores_malformed_page():
    assert _collect("<html><body>No structured fares here</body></html>") == []


def test_air_india_ignores_no_flight_and_sold_out_cards():
    html = """
    <div>Delhi to</div><div>Mumbai</div>
    <div>Fri, Sep 11, 26</div>
    <div>Sold Out</div>
    <div>INR 6,823*</div>
    """

    assert _collect(html) == []


def test_air_india_ignores_different_departure_date():
    html = """
    <div>Delhi to</div><div>Mumbai</div>
    <div>Fri, Sep 18, 26</div>
    <div>INR 6,823*</div>
    """

    assert _collect(html) == []
