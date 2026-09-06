"""Akasa Air website scraper using normal public page interaction."""

import logging
import re
from datetime import date, datetime, time, timezone
from typing import List, Optional, Sequence

from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

from backend.app.schemas.quote import RawAirfareQuoteCreate
from scraper.base.base_scraper import (
    BaseFlightScraper,
    RouteUnavailableException,
    ScraperConfig,
    ScrapingBlockedException,
    resolve_advance_window_days,
)

logger = logging.getLogger("apix.scraper.akasa")


AKASA_BOOKING_URL = "https://www.akasaair.com/flight-booking"
AKASA_SEARCH_PATH = "https://www.akasaair.com/flight-search"

AIRPORT_SEARCH_TERMS = {
    "DEL": "Delhi",
    "BOM": "Mumbai",
    "BLR": "Bengaluru",
    "CCU": "Kolkata",
    "HYD": "Hyderabad",
    "MAA": "Chennai",
}

MONTH_NAMES = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


class AkasaWebsiteScraper(BaseFlightScraper):
    """Collects visible Akasa Air public search-result fares."""

    def __init__(self, config: Optional[ScraperConfig] = None):
        cfg = config or ScraperConfig(
            source_name="Akasa Air",
            base_url=AKASA_BOOKING_URL,
            rate_limit_delay_seconds=3.0,
            timeout_seconds=45.0,
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
        """Fetch visible Akasa fares for a route/date from the public booking flow."""
        await self.verify_policy_and_rate_limit(AKASA_BOOKING_URL)
        await self.verify_policy_and_rate_limit(AKASA_SEARCH_PATH)

        collected_at = datetime.now(timezone.utc)
        origin_code = origin.upper()
        destination_code = destination.upper()

        try:
            async with async_playwright() as playwright:
                browser, context = await self.create_browser_context(playwright)
                try:
                    page = await context.new_page()
                    response = await page.goto(
                        AKASA_BOOKING_URL,
                        wait_until="domcontentloaded",
                        timeout=int(self.config.timeout_seconds * 1000),
                    )
                    if response is not None and response.status in (403, 429):
                        raise ScrapingBlockedException(f"HTTP {response.status} from Akasa Air")

                    await self._wait_for_render(page)
                    self.detect_block_or_captcha(await page.content(), await page.title())

                    await self._select_one_way(page)
                    await self._select_airport(page, field_name="From", airport_code=origin_code)
                    await self._select_airport(page, field_name="To", airport_code=destination_code)
                    await self._select_departure_date(page, departure_date)

                    search_button = page.locator('button[name="Search Flights"]')
                    if await search_button.count() == 0:
                        raise ScrapingBlockedException("Akasa search button did not render")
                    await search_button.first.click(timeout=int(self.config.timeout_seconds * 1000))

                    await self._wait_for_results(page)
                    self.detect_block_or_captcha(await page.content(), await page.title())

                    result_text = await page.locator("body").inner_text(timeout=15000)
                    quotes = self.extract_quotes_from_text(
                        result_text,
                        origin=origin_code,
                        destination=destination_code,
                        departure_date=departure_date,
                        route_id=route_id,
                        source_id=source_id,
                        cabin_class=cabin_class,
                        collected_at=collected_at,
                        requested_advance_window_days=advance_window_days,
                    )

                    await self._try_attach_selected_fare_breakdown(page, quotes, origin_code, destination_code)
                finally:
                    await context.close()
                    await browser.close()
        except PlaywrightTimeoutError as exc:
            raise ScrapingBlockedException("Akasa page timed out during normal public interaction") from exc

        if not quotes:
            raise RouteUnavailableException(
                f"No visible Akasa fare cards found for {origin_code}-{destination_code} on {departure_date}"
            )
        return quotes

    async def _wait_for_render(self, page) -> None:
        try:
            await page.wait_for_load_state(
                "networkidle",
                timeout=min(int(self.config.timeout_seconds * 1000), 15000),
            )
        except PlaywrightTimeoutError:
            logger.info("Akasa page did not reach networkidle; continuing with rendered DOM")
        await page.locator('input[name="From"]').wait_for(timeout=int(self.config.timeout_seconds * 1000))
        await page.locator('input[name="To"]').wait_for(timeout=int(self.config.timeout_seconds * 1000))

    async def _select_one_way(self, page) -> None:
        one_way = page.locator('input[name="oneway"]')
        if await one_way.count() and not await one_way.first.is_checked():
            await one_way.first.click()

    async def _select_airport(self, page, field_name: str, airport_code: str) -> None:
        search_term = AIRPORT_SEARCH_TERMS.get(airport_code, airport_code)
        field = page.locator(f'input[name="{field_name}"]')
        await field.click(timeout=int(self.config.timeout_seconds * 1000))
        await field.fill(search_term, timeout=int(self.config.timeout_seconds * 1000))
        await page.wait_for_timeout(500)

        options = await page.locator("li").element_handles()
        for option in options:
            text_content = await option.inner_text()
            normalized = re.sub(r"\s+", " ", text_content).strip()
            if not normalized.startswith(f"{airport_code} "):
                continue
            box = await option.bounding_box()
            if not box or box["width"] <= 0 or box["height"] <= 0:
                continue
            await option.click()
            await page.wait_for_timeout(500)
            return

        raise RouteUnavailableException(f"Akasa airport option {airport_code} was not visible in {field_name}")

    async def _select_departure_date(self, page, departure_date: date) -> None:
        await page.locator('button[name="SelectDepartureDate"]').click(timeout=int(self.config.timeout_seconds * 1000))
        await page.wait_for_timeout(500)

        aria_label = self._date_aria_label(departure_date)
        date_cell = page.locator(f'[aria-label="{aria_label}"]')
        if await date_cell.count() == 0:
            raise RouteUnavailableException(f"Akasa date {departure_date.isoformat()} was not visible/selectable")
        await date_cell.first.click(timeout=int(self.config.timeout_seconds * 1000))
        await page.wait_for_timeout(500)

    async def _wait_for_results(self, page) -> None:
        try:
            await page.wait_for_url("**/flight-search", timeout=int(self.config.timeout_seconds * 1000))
        except PlaywrightTimeoutError:
            logger.info("Akasa did not change URL to /flight-search before timeout; inspecting current page")

        await page.wait_for_function(
            "() => /QP\\d{3,4}/.test(document.body.innerText || '')",
            timeout=int(self.config.timeout_seconds * 1000),
        )

    async def _try_attach_selected_fare_breakdown(
        self,
        page,
        quotes: List[RawAirfareQuoteCreate],
        origin: str,
        destination: str,
    ) -> None:
        """Select first parsed fare and update its base/tax fields if summary is visible."""
        if not quotes:
            return
        first = quotes[0]
        try:
            fare_cards = page.locator('[aria-label="flight card"]')
            for idx in range(await fare_cards.count()):
                card_text = await fare_cards.nth(idx).inner_text(timeout=3000)
                if (
                    first.flight_number
                    and first.flight_number in card_text
                    and f"\n{origin}\n" not in card_text
                    and f"\n{destination}\n" not in card_text
                ):
                    continue
                if first.flight_number and first.flight_number not in card_text:
                    continue
                await fare_cards.nth(idx).click(timeout=5000)
                break

            summary = page.get_by_text("View summary", exact=True)
            if await summary.count():
                await summary.first.click(timeout=5000)
                await page.wait_for_timeout(1000)

            summary_text = await page.locator("body").inner_text(timeout=5000)
        except Exception as exc:  # pragma: no cover - best-effort enrichment
            logger.info("Akasa fare-summary enrichment skipped: %s", exc)
            return

        base_fare, taxes_fees = self.parse_summary_components(summary_text)
        if base_fare is not None and taxes_fees is not None:
            first.base_fare = round(base_fare, 2)
            first.taxes_fees = round(taxes_fees, 2)

    @classmethod
    def extract_quotes_from_text(
        cls,
        rendered_text: str,
        origin: str,
        destination: str,
        departure_date: date,
        route_id: int,
        source_id: Optional[int],
        cabin_class: str,
        collected_at: datetime,
        requested_advance_window_days: Optional[int] = None,
    ) -> List[RawAirfareQuoteCreate]:
        """Parse Akasa result text into RawAirfareQuoteCreate objects."""
        lines = cls._visible_lines(rendered_text)
        if not cls._selection_header_matches(lines, origin, destination, departure_date):
            return []

        target_origin = origin.upper()
        target_destination = destination.upper()
        quotes: List[RawAirfareQuoteCreate] = []

        for block in cls._flight_blocks(lines):
            flight_number = block[0]
            parsed = cls._parse_flight_block(block, target_origin, target_destination)
            if parsed is None:
                continue

            total_fare = parsed["total_fare"]
            if total_fare <= 0:
                continue

            departure_time = parsed["departure_time"]
            arrival_time = parsed["arrival_time"]
            advance_window_days = resolve_advance_window_days(
                departure_date,
                collected_at,
                requested_advance_window_days,
            )
            quotes.append(
                RawAirfareQuoteCreate(
                    source_id=source_id,
                    route_id=route_id,
                    flight_number=flight_number,
                    departure_datetime=datetime.combine(departure_date, departure_time, tzinfo=timezone.utc),
                    arrival_datetime=datetime.combine(departure_date, arrival_time, tzinfo=timezone.utc),
                    advance_window_days=advance_window_days,
                    base_fare=0.0,
                    taxes_fees=0.0,
                    total_fare=round(float(total_fare), 2),
                    cabin_class=cls._cabin_value(cabin_class, parsed.get("fare_product")),
                    scraped_at=collected_at,
                )
            )

        return quotes

    @staticmethod
    def _flight_blocks(lines: Sequence[str]) -> List[Sequence[str]]:
        blocks: List[Sequence[str]] = []
        flight_indexes = [idx for idx, line in enumerate(lines) if re.fullmatch(r"QP\d{3,4}", line)]
        for pos, start in enumerate(flight_indexes):
            end = flight_indexes[pos + 1] if pos + 1 < len(flight_indexes) else len(lines)
            blocks.append(lines[start:end])
        return blocks

    @staticmethod
    def _parse_flight_block(
        block: Sequence[str],
        target_origin: str,
        target_destination: str,
    ) -> Optional[dict]:
        if len(block) < 8 or not re.fullmatch(r"QP\d{3,4}", block[0]):
            return None

        origin_idx = AkasaWebsiteScraper._find_airport_index(block, target_origin, start=1)
        if origin_idx is None:
            return None

        destination_idx = AkasaWebsiteScraper._find_airport_index(block, target_destination, start=origin_idx + 1)
        if destination_idx is None:
            return None

        departure_time = AkasaWebsiteScraper._nearest_time_before(block, origin_idx)
        arrival_time = AkasaWebsiteScraper._arrival_time_between(block, origin_idx, destination_idx)
        if departure_time is None or arrival_time is None:
            return None

        total_fare = AkasaWebsiteScraper._parse_total_fare(block, destination_idx)
        if total_fare is None:
            return None

        fare_product = None
        for line in block:
            if line.lower() in {"saver", "flexi"}:
                fare_product = line
        return {
            "departure_time": departure_time,
            "arrival_time": arrival_time,
            "total_fare": total_fare,
            "fare_product": fare_product,
        }

    @staticmethod
    def _find_airport_index(block: Sequence[str], airport_code: str, start: int) -> Optional[int]:
        target = airport_code.upper()
        for idx in range(start, len(block)):
            if block[idx].upper() == target:
                return idx
        return None

    @staticmethod
    def _nearest_time_before(block: Sequence[str], marker_idx: int) -> Optional[time]:
        for idx in range(marker_idx - 1, 0, -1):
            parsed = AkasaWebsiteScraper._parse_time(block[idx])
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _arrival_time_between(block: Sequence[str], origin_idx: int, destination_idx: int) -> Optional[time]:
        segment = block[origin_idx + 1 : destination_idx]
        search_start = 0
        for idx, line in enumerate(segment):
            if "stop" in line.lower():
                search_start = idx + 1

        for line in segment[search_start:]:
            parsed = AkasaWebsiteScraper._parse_time(line)
            if parsed is not None:
                return parsed

        for line in segment:
            parsed = AkasaWebsiteScraper._parse_time(line)
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _parse_total_fare(block: Sequence[str], destination_idx: int) -> Optional[float]:
        for idx, line in enumerate(block):
            if line.lower() not in {"starting", "you pay"}:
                continue
            for candidate in block[idx + 1 : idx + 4]:
                amount = AkasaWebsiteScraper.parse_money(candidate)
                if amount is not None:
                    return amount

        for line in block[destination_idx + 1 :]:
            if "earn" in line.lower() or "point" in line.lower():
                continue
            amount = AkasaWebsiteScraper.parse_money(line)
            if amount is not None:
                return amount
        return None

    @staticmethod
    def parse_summary_components(rendered_text: str) -> tuple[Optional[float], Optional[float]]:
        """Extract base fare and aggregate taxes/fees from an opened fare summary."""
        lines = AkasaWebsiteScraper._visible_lines(rendered_text)
        try:
            start = lines.index("Fare breakdown")
        except ValueError:
            return None, None

        summary_lines = lines[start : start + 30]
        base_fare = None
        taxes_total = 0.0
        in_tax_section = False
        tax_labels = {
            "CUTE Fees",
            "RCS & Admin Charge",
            "Aviation Security Fee",
            "User Development Fee - Departure",
            "User Development Fee - Arrival",
            "Tax",
        }

        for idx, line in enumerate(summary_lines):
            if line == "1 X Adult" and idx + 1 < len(summary_lines):
                base_fare = AkasaWebsiteScraper.parse_money(summary_lines[idx + 1])
            if line == "Taxes & fees":
                in_tax_section = True
                continue
            if in_tax_section and line in tax_labels and idx + 1 < len(summary_lines):
                amount = AkasaWebsiteScraper.parse_money(summary_lines[idx + 1])
                if amount is not None:
                    taxes_total += amount

        if base_fare is None:
            return None, None
        return base_fare, taxes_total

    @staticmethod
    def parse_money(value: str) -> Optional[float]:
        match = re.search(r"(?:INR|Rs\.?|₹)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", value, flags=re.IGNORECASE)
        if not match:
            match = re.search(r"₹\s*([0-9][0-9,]*(?:\.[0-9]+)?)", value)
        if not match:
            return None
        return float(match.group(1).replace(",", ""))

    @staticmethod
    def _visible_lines(rendered_text: str) -> List[str]:
        return [
            re.sub(r"\s+", " ", raw_line).strip()
            for raw_line in rendered_text.splitlines()
            if re.sub(r"\s+", " ", raw_line).strip()
        ]

    @staticmethod
    def _selection_header_matches(lines: Sequence[str], origin: str, destination: str, departure_date: date) -> bool:
        route_label = f"{AkasaWebsiteScraper._airport_city(origin)} - {AkasaWebsiteScraper._airport_city(destination)}"
        weekday = departure_date.strftime("%a")
        month = departure_date.strftime("%b")
        date_labels = {
            f"{weekday}, {departure_date.day} {month}",
            f"{weekday}, {departure_date.day:02d} {month}",
        }
        for idx, line in enumerate(lines[:20]):
            if route_label not in line:
                continue
            nearby = lines[idx : idx + 4]
            return any(any(date_label in item for date_label in date_labels) and "Passenger" in item for item in nearby)
        return False

    @staticmethod
    def _airport_city(code: str) -> str:
        return AIRPORT_SEARCH_TERMS.get(code.upper(), code.upper())

    @staticmethod
    def _parse_time(value: str) -> Optional[time]:
        try:
            return datetime.strptime(value.strip(), "%H:%M").time()
        except ValueError:
            return None

    @staticmethod
    def _cabin_value(cabin_class: str, fare_product: Optional[str]) -> str:
        cabin = cabin_class.upper()
        if fare_product:
            value = f"{cabin}-{fare_product.upper()}"
            return value[:30]
        return cabin[:30]

    @staticmethod
    def _date_aria_label(target_date: date) -> str:
        return f"Choose {target_date.strftime('%A')}, {MONTH_NAMES[target_date.month]} {AkasaWebsiteScraper._ordinal(target_date.day)}, {target_date.year}"

    @staticmethod
    def _ordinal(day: int) -> str:
        if 10 <= day % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        return f"{day}{suffix}"
