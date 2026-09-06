"""Tests for Akasa visible-result parsing and compliance guards."""

from datetime import date, datetime, timezone
from typing import Optional

import pytest

from scraper.airlines.akasa_scraper import AkasaWebsiteScraper
from scraper.base.base_scraper import (
    CaptchaDetectedException,
    RobotsDisallowedException,
    ScraperConfig,
    ScrapingBlockedException,
)


AKASA_RESULT_TEXT = """
Book
One Way: Delhi - Mumbai
Fri, 11 Sep • 1 Passenger(s)
₹ INR
Fri, 11 Sep
₹6,530
QP2074
14:10
DEL
(Terminal 1)
2h 5m
Non-stop
16:15
NMI
(Terminal 1)
Lowest fare
Starting
₹6,500
QP1833
06:50
DEL
(Terminal 1)
2h 20m
Non-stop
09:10
BOM
(Terminal 2)
Starting
₹6,530
+ Earn upto 1014 Elevate Points per member
QP1119
08:40
DEL
(Terminal 1)
2h 25m
Non-stop
11:05
BOM
(Terminal 2)
Starting
₹6,530
QP1940
14:05
DXN
2h 15m
Non-stop
16:20
BOM
(Terminal 2)
Starting
₹6,618
"""
AKASA_T1_RESULT_TEXT = """
Book
One Way: Delhi - Mumbai
Sat, 05 Sep \u2022 1 Passenger(s)
\u20b9 INR
Sat, 05 Sep
\u20b96,530
QP1110
10:30
DEL
(Terminal 1)
2h 15m
Non-stop
12:39
12:45
BOM
(Terminal 2)
Lowest fare
Starting
\u20b96,530
+ Earn upto 1014 Elevate Points per member
QP1836
12:30
DEL
(Terminal 1)
2h 25m
Non-stop
14:39
14:55
BOM
(Terminal 2)
Starting
\u20b96,530
+ Earn upto 1014 Elevate Points per member
QP1128
16:00
DEL
(Terminal 1)
2h 20m
Non-stop
18:08
18:20
BOM
(Terminal 2)
Starting
\u20b96,530
+ Earn upto 1014 Elevate Points per member
QP1820
17:30
DEL
(Terminal 1)
2h 15m
Non-stop
19:45
BOM
(Terminal 2)
Starting
\u20b96,530
+ Earn upto 1014 Elevate Points per member
QP1826
19:55
DEL
(Terminal 1)
2h 25m
Non-stop
22:20
BOM
(Terminal 2)
Starting
\u20b96,530
+ Earn upto 1014 Elevate Points per member
QP1940
14:05
DXN
2h 15m
Non-stop
16:12
16:20
BOM
(Terminal 2)
Starting
\u20b96,618
+ Earn upto 956 Elevate Points per member
"""


def _collect(rendered_text: str = AKASA_RESULT_TEXT, departure: date = date(2026, 9, 11)):
    return AkasaWebsiteScraper.extract_quotes_from_text(
        rendered_text,
        origin="DEL",
        destination="BOM",
        departure_date=departure,
        route_id=1,
        source_id=4,
        cabin_class="ECONOMY",
        collected_at=datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc),
    )


def test_akasa_extracts_visible_del_bom_fares():
    quotes = _collect()

    assert [q.flight_number for q in quotes] == ["QP1833", "QP1119"]
    assert quotes[0].route_id == 1
    assert quotes[0].source_id == 4
    assert quotes[0].departure_datetime.isoformat() == "2026-09-11T06:50:00+00:00"
    assert quotes[0].arrival_datetime.isoformat() == "2026-09-11T09:10:00+00:00"
    assert quotes[0].advance_window_days == 7
    assert quotes[0].total_fare == 6530.0
    assert quotes[0].base_fare == 0.0
    assert quotes[0].taxes_fees == 0.0
    assert quotes[0].cabin_class == "ECONOMY"


def test_akasa_selected_date_matches_zero_padded_day():
    lines = AkasaWebsiteScraper._visible_lines(
        """
        Book
        One Way: Delhi - Mumbai
        Sat, 05 Sep \u2022 1 Passenger(s)
        """
    )

    assert AkasaWebsiteScraper._selection_header_matches(lines, "DEL", "BOM", date(2026, 9, 5))


def test_akasa_selected_date_matches_non_zero_padded_day():
    lines = AkasaWebsiteScraper._visible_lines(
        """
        Book
        One Way: Delhi - Mumbai
        Sat, 5 Sep \u2022 1 Passenger(s)
        """
    )

    assert AkasaWebsiteScraper._selection_header_matches(lines, "DEL", "BOM", date(2026, 9, 5))


def test_akasa_extracts_t1_cards_with_dual_arrival_times():
    quotes = _collect(AKASA_T1_RESULT_TEXT, departure=date(2026, 9, 5))

    assert [quote.flight_number for quote in quotes] == ["QP1110", "QP1836", "QP1128", "QP1820", "QP1826"]
    assert [quote.total_fare for quote in quotes] == [6530.0, 6530.0, 6530.0, 6530.0, 6530.0]
    assert quotes[0].departure_datetime.isoformat() == "2026-09-05T10:30:00+00:00"
    assert quotes[0].arrival_datetime.isoformat() == "2026-09-05T12:39:00+00:00"
    assert quotes[1].arrival_datetime.isoformat() == "2026-09-05T14:39:00+00:00"
    assert quotes[2].arrival_datetime.isoformat() == "2026-09-05T18:08:00+00:00"


def test_akasa_filters_nearby_airports():
    quotes = _collect()

    assert "QP2074" not in {q.flight_number for q in quotes}  # DEL-NMI
    assert "QP1940" not in {q.flight_number for q in quotes}  # DXN-BOM


def test_akasa_rejects_t1_dxn_bom_nearby_airport_result():
    quotes = _collect(AKASA_T1_RESULT_TEXT, departure=date(2026, 9, 5))

    assert "QP1940" not in {quote.flight_number for quote in quotes}


def test_akasa_filters_route_and_selected_date_header():
    wrong_route_text = AKASA_RESULT_TEXT.replace("One Way: Delhi - Mumbai", "One Way: Delhi - Bengaluru")
    wrong_date_text = AKASA_RESULT_TEXT.replace("Fri, 11 Sep • 1 Passenger(s)", "Fri, 18 Sep • 1 Passenger(s)")

    assert _collect(wrong_route_text) == []
    assert _collect(wrong_date_text) == []


def test_akasa_advance_window_calculation_clamps_at_zero():
    quotes = AkasaWebsiteScraper.extract_quotes_from_text(
        AKASA_RESULT_TEXT,
        origin="DEL",
        destination="BOM",
        departure_date=date(2026, 9, 11),
        route_id=1,
        source_id=4,
        cabin_class="ECONOMY",
        collected_at=datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc),
    )

    assert quotes[0].advance_window_days == 0


def test_akasa_uses_requested_advance_window_context():
    quotes = AkasaWebsiteScraper.extract_quotes_from_text(
        AKASA_RESULT_TEXT,
        origin="DEL",
        destination="BOM",
        departure_date=date(2026, 9, 11),
        route_id=1,
        source_id=4,
        cabin_class="ECONOMY",
        collected_at=datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc),
        requested_advance_window_days=7,
    )

    assert quotes[0].advance_window_days == 7


def test_akasa_fare_parsing_and_summary_components():
    assert AkasaWebsiteScraper.parse_money("₹11,124") == 11124.0
    assert AkasaWebsiteScraper.parse_money("INR 6,530") == 6530.0

    base, taxes = AkasaWebsiteScraper.parse_summary_components(
        """
        Fare summary
        Fare breakdown
        1 X Adult
        ₹5,640
        Taxes & fees
        CUTE Fees
        ₹75
        RCS & Admin Charge
        ₹50
        Aviation Security Fee
        ₹236
        User Development Fee - Departure
        ₹152
        User Development Fee - Arrival
        ₹89
        Tax
        ₹288
        You Pay
        ₹6,530
        """
    )

    assert base == 5640.0
    assert taxes == 890.0


def test_akasa_missing_base_tax_handling_keeps_zeroes():
    quote = _collect()[0]

    assert quote.base_fare == 0.0
    assert quote.taxes_fees == 0.0


def test_akasa_captcha_and_block_detection():
    scraper = AkasaWebsiteScraper()

    with pytest.raises(CaptchaDetectedException):
        scraper.detect_block_or_captcha("<html>hcaptcha challenge</html>", "Akasa")

    with pytest.raises(ScrapingBlockedException):
        scraper.detect_block_or_captcha("<html>Access Denied</html>", "Akasa")


def test_akasa_date_aria_label():
    assert AkasaWebsiteScraper._date_aria_label(date(2026, 9, 11)) == "Choose Friday, September 11th, 2026"
    assert AkasaWebsiteScraper._date_aria_label(date(2026, 9, 1)) == "Choose Tuesday, September 1st, 2026"
    assert AkasaWebsiteScraper._date_aria_label(date(2026, 9, 2)) == "Choose Wednesday, September 2nd, 2026"
    assert AkasaWebsiteScraper._date_aria_label(date(2026, 9, 3)) == "Choose Thursday, September 3rd, 2026"


class DisallowRobots:
    async def is_allowed(self, target_url: str, user_agent: Optional[str] = None) -> bool:
        return False

    async def get_crawl_delay(self, target_url: str, user_agent: Optional[str] = None):
        return None


class NoopRateLimiter:
    def set_domain_delay(self, target_url: str, delay: float) -> None:
        pass

    async def wait(self, target_url: str, override_delay: Optional[float] = None) -> None:
        pass


@pytest.mark.asyncio
async def test_akasa_robots_disallowed_stops_before_browser():
    scraper = AkasaWebsiteScraper(
        ScraperConfig(source_name="Akasa Air", base_url="https://www.akasaair.com/flight-booking")
    )
    scraper.robots_checker = DisallowRobots()
    scraper.rate_limiter = NoopRateLimiter()

    with pytest.raises(RobotsDisallowedException):
        await scraper.fetch_quotes("DEL", "BOM", date(2026, 9, 11), route_id=1, source_id=4)


def test_akasa_raw_quote_mapping():
    quote = _collect()[0]
    data = quote.model_dump()

    assert data["route_id"] == 1
    assert data["source_id"] == 4
    assert data["flight_number"] == "QP1833"
    assert data["departure_datetime"] == datetime(2026, 9, 11, 6, 50, tzinfo=timezone.utc)
    assert data["arrival_datetime"] == datetime(2026, 9, 11, 9, 10, tzinfo=timezone.utc)
    assert data["advance_window_days"] == 7
    assert data["total_fare"] == 6530.0
    assert data["scraped_at"] == datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
