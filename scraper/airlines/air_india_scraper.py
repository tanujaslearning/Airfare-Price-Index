"""Air India website scraper using normal public page rendering."""

import html
import logging
import re
from datetime import date, datetime, time, timezone
from typing import List, Optional

from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

from backend.app.schemas.quote import RawAirfareQuoteCreate
from scraper.base.base_scraper import (
    BaseFlightScraper,
    RouteUnavailableException,
    ScraperConfig,
    ScrapingBlockedException,
    resolve_advance_window_days,
)

logger = logging.getLogger("apix.scraper.air_india")


CITY_CODE_MAP = {
    "ahmedabad": "AMD",
    "bengaluru": "BLR",
    "bangalore": "BLR",
    "chennai": "MAA",
    "delhi": "DEL",
    "goa": "GOI",
    "hyderabad": "HYD",
    "kolkata": "CCU",
    "mumbai": "BOM",
    "pune": "PNQ",
}

AIR_INDIA_BOOKING_URL = "https://www.airindia.com/en-in/book-flights/"


class AirIndiaWebsiteScraper(BaseFlightScraper):
    """Collects visible public fare cards from Air India's normal website page."""

    def __init__(self, config: Optional[ScraperConfig] = None):
        cfg = config or ScraperConfig(
            source_name="Air India",
            base_url=AIR_INDIA_BOOKING_URL,
            rate_limit_delay_seconds=3.0,
        )
        super().__init__(cfg)

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
        """Fetch visible fare quotes for a route/date from Air India's public page."""
        target_url = self.config.base_url
        await self.verify_policy_and_rate_limit(target_url)

        collected_at = datetime.now(timezone.utc)
        try:
            async with async_playwright() as playwright:
                browser, context = await self.create_browser_context(playwright)
                try:
                    page = await context.new_page()
                    response = await page.goto(
                        target_url,
                        wait_until="domcontentloaded",
                        timeout=int(self.config.timeout_seconds * 1000),
                    )
                    if response is not None and response.status in (403, 429):
                        raise ScrapingBlockedException(f"HTTP {response.status} from Air India")

                    try:
                        await page.wait_for_load_state(
                            "networkidle",
                            timeout=min(int(self.config.timeout_seconds * 1000), 10000),
                        )
                    except PlaywrightTimeoutError:
                        logger.info("Air India page did not reach networkidle; continuing with rendered DOM")

                    page_title = await page.title()
                    content = await page.content()
                    self.detect_block_or_captcha(content, page_title)
                finally:
                    await context.close()
                    await browser.close()
        except PlaywrightTimeoutError as exc:
            raise ScrapingBlockedException("Air India page timed out during normal rendering") from exc

        quotes = self.extract_quotes_from_html(
            content,
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            route_id=route_id,
            source_id=source_id,
            cabin_class=cabin_class,
            collected_at=collected_at,
            requested_advance_window_days=advance_window_days,
        )
        if not quotes:
            raise RouteUnavailableException(
                f"No visible Air India fare cards found for {origin}-{destination} on {departure_date}"
            )
        return quotes

    @classmethod
    def extract_quotes_from_html(
        cls,
        page_html: str,
        origin: str,
        destination: str,
        departure_date: date,
        route_id: int,
        source_id: Optional[int],
        cabin_class: str,
        collected_at: datetime,
        requested_advance_window_days: Optional[int] = None,
    ) -> List[RawAirfareQuoteCreate]:
        """Parse visible route/date/fare cards from already-rendered HTML."""
        lines = cls._visible_lines(page_html)
        target_origin = origin.upper()
        target_destination = destination.upper()
        quotes: List[RawAirfareQuoteCreate] = []

        for idx, line in enumerate(lines):
            pair = cls._parse_route_pair(lines, idx)
            if pair is None:
                continue

            origin_code, destination_code = pair
            if origin_code != target_origin or destination_code != target_destination:
                continue

            window = lines[idx : idx + 18]
            if any("sold out" in item.lower() or "cancelled" in item.lower() for item in window):
                continue

            visible_departure_date = cls._parse_departure_date(window)
            if visible_departure_date != departure_date:
                continue

            total_fare = cls._parse_total_fare(window)
            if total_fare is None or total_fare <= 0:
                continue

            base_fare = cls._parse_component(window, ("base fare", "base"))
            taxes_fees = cls._parse_component(window, ("tax", "taxes", "fee", "fees"))
            if base_fare is None or taxes_fees is None:
                base_fare = 0.0
                taxes_fees = 0.0

            advance_window_days = resolve_advance_window_days(
                departure_date,
                collected_at,
                requested_advance_window_days,
            )
            quotes.append(
                RawAirfareQuoteCreate(
                    source_id=source_id,
                    route_id=route_id,
                    flight_number=cls._parse_flight_number(window),
                    departure_datetime=datetime.combine(departure_date, time.min, tzinfo=timezone.utc),
                    arrival_datetime=None,
                    advance_window_days=advance_window_days,
                    base_fare=round(float(base_fare), 2),
                    taxes_fees=round(float(taxes_fees), 2),
                    total_fare=round(float(total_fare), 2),
                    cabin_class=cabin_class.upper(),
                    scraped_at=collected_at,
                )
            )

        return quotes

    @staticmethod
    def _visible_lines(page_html: str) -> List[str]:
        without_scripts = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", page_html)
        with_breaks = re.sub(r"(?i)<br\s*/?>|</(p|div|li|td|th|tr|h[1-6])>", "\n", without_scripts)
        text = re.sub(r"<[^>]+>", " ", with_breaks)
        text = html.unescape(text)
        lines = []
        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if line:
                lines.append(line)
        return lines

    @staticmethod
    def _parse_route_pair(lines: List[str], idx: int) -> Optional[tuple[str, str]]:
        line = lines[idx]
        compact_match = re.search(r"\(([A-Z]{3})\)\s*to\s*(?:.+?)?\(([A-Z]{3})\)", line)
        if compact_match:
            return compact_match.group(1), compact_match.group(2)

        code_match = re.search(r"\b([A-Z]{3})\s*(?:-|to|→)\s*([A-Z]{3})\b", line)
        if code_match:
            return code_match.group(1), code_match.group(2)

        city_match = re.match(r"^([A-Za-z ]+)\s+to$", line, flags=re.IGNORECASE)
        if city_match and idx + 1 < len(lines):
            origin_code = CITY_CODE_MAP.get(city_match.group(1).strip().lower())
            destination_code = CITY_CODE_MAP.get(lines[idx + 1].strip().lower())
            if origin_code and destination_code:
                return origin_code, destination_code

        return None

    @staticmethod
    def _parse_departure_date(lines: List[str]) -> Optional[date]:
        for line in lines:
            clean = re.sub(r"^Depart:\s*", "", line.strip(), flags=re.IGNORECASE)
            clean = re.sub(r"\s+", " ", clean.replace(",", ""))
            for fmt in ("%a %b %d %y", "%a %b %d %Y", "%b %d %y", "%b %d %Y"):
                try:
                    return datetime.strptime(clean, fmt).date()
                except ValueError:
                    continue
        return None

    @staticmethod
    def _parse_money(value: str) -> Optional[float]:
        match = re.search(r"(?:INR|₹|Rs\.?)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", value, flags=re.IGNORECASE)
        if not match:
            return None
        return float(match.group(1).replace(",", ""))

    @classmethod
    def _parse_total_fare(cls, lines: List[str]) -> Optional[float]:
        prioritized = [
            line for line in lines
            if re.search(r"\b(total|from|economy from|price)\b", line, flags=re.IGNORECASE)
        ]
        for line in prioritized + lines:
            amount = cls._parse_money(line)
            if amount is not None:
                return amount
        return None

    @classmethod
    def _parse_component(cls, lines: List[str], labels: tuple[str, ...]) -> Optional[float]:
        for line in lines:
            lower = line.lower()
            if any(label in lower for label in labels):
                amount = cls._parse_money(line)
                if amount is not None:
                    return amount
        return None

    @staticmethod
    def _parse_flight_number(lines: List[str]) -> Optional[str]:
        joined = " ".join(lines)
        match = re.search(r"\bAI[- ]?([0-9]{2,4})\b", joined, flags=re.IGNORECASE)
        if not match:
            return None
        return f"AI-{match.group(1)}"
