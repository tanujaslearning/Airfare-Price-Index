"""SpiceJet public booking-form interaction helpers.

The scraper uses the normal public booking flow and parses only the rendered
result page. It does not read booking API responses as a substitute for visible
results.
"""

import logging
import re
import time as monotonic_time
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, List, Optional, Sequence

from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

from backend.app.schemas.quote import RawAirfareQuoteCreate
from scraper.base.base_scraper import (
    BaseFlightScraper,
    RouteUnavailableException,
    ScraperConfig,
    ScrapingBlockedException,
    ScrapingException,
    resolve_advance_window_days,
)

logger = logging.getLogger("apix.scraper.spicejet")


SPICEJET_HOME_URL = "https://www.spicejet.com/"
SEARCH_SUCCESS = "SEARCH_SUCCESS"
SEARCH_INTERACTION_TRANSIENT_FAILURE = "SEARCH_INTERACTION_TRANSIENT_FAILURE"
SEARCH_NAVIGATION_TIMEOUT = "SEARCH_NAVIGATION_TIMEOUT"
SEARCH_RESULTS_UI_MISSING = "SEARCH_RESULTS_UI_MISSING"
CLIENT_SIDE_VALIDATION = "CLIENT_SIDE_VALIDATION"
FORM_STATE_NOT_READY = "FORM_STATE_NOT_READY"
CAPTCHA_DETECTED = "CAPTCHA_DETECTED"
SCRAPING_BLOCKED = "SCRAPING_BLOCKED"
UNKNOWN_SEARCH_INTERACTION_FAILURE = "UNKNOWN"

AIRPORT_CITY_LABELS = {
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


@dataclass(frozen=True)
class SpiceJetAirportOption:
    """Visible airport option selected from the public autocomplete."""

    airport_code: str
    city: str
    text: str
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class SpiceJetSelectionEvidence:
    """Evidence that an airport selection is committed, not only typed."""

    field_label: str
    airport_code: str
    field_text: str
    option_clicked: bool
    retained_after_blur: bool
    autocomplete_open: bool
    validation_error_visible: bool = False


@dataclass(frozen=True)
class SpiceJetSearchReachability:
    """Outcome of the controlled public search interaction."""

    final_url: str
    page_title: str
    search_submitted: bool
    results_page_reached: bool
    flight_card_count: int
    visible_flight_numbers: List[str]


@dataclass(frozen=True)
class SpiceJetSearchFormState:
    """Pre-click booking-form state captured from the rendered public page."""

    origin_committed: bool
    destination_committed: bool
    departure_date_committed: bool
    one_way_selected: bool
    adult_count: int
    currency: str
    search_enabled: bool
    validation_error_visible: bool
    page_ready: bool
    button_text: str
    button_attributes: dict[str, Any]

    @property
    def is_ready(self) -> bool:
        return (
            self.origin_committed
            and self.destination_committed
            and self.departure_date_committed
            and self.one_way_selected
            and self.adult_count == 1
            and self.currency.upper() == "INR"
            and self.search_enabled
            and not self.validation_error_visible
            and self.page_ready
        )


@dataclass(frozen=True)
class SpiceJetSearchOutcome:
    """Post-click search-state outcome from normal public browser observation."""

    classification: str
    final_url: str
    navigation_detected: bool
    results_rendered: bool
    flight_card_count: int = 0
    visible_error: Optional[str] = None
    request_statuses: tuple[int, ...] = ()
    request_failures: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        return self.classification == SEARCH_SUCCESS and self.results_rendered


class SpiceJetSearchInteractionError(ScrapingException):
    """Raised when the SpiceJet public UI search cannot reach rendered results."""

    def __init__(self, classification: str, message: str):
        self.classification = classification
        super().__init__(f"{classification}: {message}")


@dataclass(frozen=True)
class SpiceJetParsedFlight:
    """Visible flight/fare-family result parsed from one result row."""

    flight_number: str
    origin: str
    destination: str
    departure_time: time
    arrival_time: time
    arrival_next_day: bool
    fare_family: str
    total_fare: float


class SpiceJetWebsiteScraper(BaseFlightScraper):
    """Collects visible SpiceJet result-page fares."""

    def __init__(self, config: Optional[ScraperConfig] = None):
        cfg = config or ScraperConfig(
            source_name="SpiceJet",
            base_url=SPICEJET_HOME_URL,
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
        """Fetch visible SpiceJet fares for a route/date from the public booking flow."""
        await self.verify_policy_and_rate_limit(SPICEJET_HOME_URL)

        collected_at = datetime.now(timezone.utc)
        origin_code = origin.upper()
        destination_code = destination.upper()

        try:
            async with async_playwright() as playwright:
                browser, context = await self.create_browser_context(playwright)
                try:
                    page = await context.new_page()
                    response = await page.goto(
                        SPICEJET_HOME_URL,
                        wait_until="domcontentloaded",
                        timeout=int(self.config.timeout_seconds * 1000),
                    )
                    if response is not None and response.status in (403, 429):
                        raise ScrapingBlockedException(f"HTTP {response.status} from SpiceJet")

                    await self._wait_for_homepage(page)
                    self.detect_block_or_captcha(await page.content(), await page.title())

                    await self._run_search_interaction(page, origin_code, destination_code, departure_date)
                    self.detect_block_or_captcha(await page.content(), await page.title())

                    result_text = await self._result_page_text(page)
                finally:
                    await context.close()
                    await browser.close()
        except PlaywrightTimeoutError as exc:
            raise ScrapingBlockedException("SpiceJet page timed out during normal public interaction") from exc

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
        if not quotes:
            raise RouteUnavailableException(
                f"No visible SpiceJet fare cards found for {origin_code}-{destination_code} on {departure_date}"
            )
        return quotes

    async def validate_search_reachability(
        self,
        origin: str,
        destination: str,
        departure_date: date,
    ) -> SpiceJetSearchReachability:
        """Run one controlled public search and report whether results are reachable."""
        await self.verify_policy_and_rate_limit(SPICEJET_HOME_URL)

        async with async_playwright() as playwright:
            browser, context = await self.create_browser_context(playwright)
            try:
                page = await context.new_page()
                response = await page.goto(
                    SPICEJET_HOME_URL,
                    wait_until="domcontentloaded",
                    timeout=int(self.config.timeout_seconds * 1000),
                )
                if response is not None and response.status in (403, 429):
                    raise ScrapingBlockedException(f"HTTP {response.status} from SpiceJet")

                await self._wait_for_homepage(page)
                self.detect_block_or_captcha(await page.content(), await page.title())

                await self._run_search_interaction(page, origin.upper(), destination.upper(), departure_date)
                self.detect_block_or_captcha(await page.content(), await page.title())

                body_text = await page.locator("body").inner_text(timeout=15000)
                flight_numbers = sorted(set(re.findall(r"\bSG\s?\d{2,4}\b", body_text, flags=re.IGNORECASE)))
                card_count = await self._count_visible_flight_cards(page, body_text)
                return SpiceJetSearchReachability(
                    final_url=page.url,
                    page_title=await page.title(),
                    search_submitted=True,
                    results_page_reached=self._looks_like_result_state(page.url, body_text),
                    flight_card_count=card_count,
                    visible_flight_numbers=flight_numbers,
                )
            except PlaywrightTimeoutError as exc:
                raise ScrapingException("SpiceJet timed out during controlled public interaction") from exc
            finally:
                await context.close()
                await browser.close()

    async def _run_search_interaction(
        self,
        page,
        origin: str,
        destination: str,
        departure_date: date,
    ) -> SpiceJetSearchOutcome:
        """Submit the public search form with one bounded normal-UI recovery."""
        last_outcome: Optional[SpiceJetSearchOutcome] = None

        for attempt_number in (1, 2):
            if attempt_number == 2:
                logger.warning(
                    "SpiceJet recovery attempted",
                    extra={"event": "spicejet_recovery_attempted", "classification": last_outcome.classification if last_outcome else None},
                )
                await self._reestablish_homepage_for_recovery(page)

            form_state = await self._prepare_and_verify_search_form(page, origin, destination, departure_date)
            logger.info(
                "SpiceJet form committed",
                extra={
                    "event": "spicejet_form_committed",
                    "attempt": attempt_number,
                    "origin": origin,
                    "destination": destination,
                    "departure_date": departure_date.isoformat(),
                    "adult_count": form_state.adult_count,
                    "currency": form_state.currency,
                },
            )

            try:
                outcome = await self._submit_search_attempt(page, attempt_number)
            except PlaywrightTimeoutError as exc:
                outcome = SpiceJetSearchOutcome(
                    classification=SEARCH_NAVIGATION_TIMEOUT,
                    final_url=getattr(page, "url", ""),
                    navigation_detected=False,
                    results_rendered=False,
                    visible_error=str(exc),
                )
            except ScrapingBlockedException:
                logger.warning("SpiceJet CAPTCHA/block detected", extra={"event": "spicejet_block_detected", "attempt": attempt_number})
                raise

            if outcome.succeeded:
                logger.info(
                    "SpiceJet results detected",
                    extra={
                        "event": "spicejet_results_detected",
                        "attempt": attempt_number,
                        "final_url": outcome.final_url,
                        "flight_card_count": outcome.flight_card_count,
                    },
                )
                if attempt_number == 2:
                    logger.info("SpiceJet recovery succeeded", extra={"event": "spicejet_recovery_succeeded"})
                return outcome

            logger.warning(
                "SpiceJet transient search failure",
                extra={
                    "event": "spicejet_transient_failure",
                    "attempt": attempt_number,
                    "classification": outcome.classification,
                    "final_url": outcome.final_url,
                    "navigation_detected": outcome.navigation_detected,
                },
            )
            last_outcome = outcome

        classification = last_outcome.classification if last_outcome else UNKNOWN_SEARCH_INTERACTION_FAILURE
        logger.error(
            "SpiceJet recovery failed",
            extra={"event": "spicejet_recovery_failed", "classification": classification},
        )
        raise SpiceJetSearchInteractionError(
            classification,
            "SpiceJet public search did not reach a rendered results page after one recovery attempt",
        )

    async def _prepare_and_verify_search_form(
        self,
        page,
        origin: str,
        destination: str,
        departure_date: date,
    ) -> SpiceJetSearchFormState:
        await self._wait_for_homepage(page)
        self.detect_block_or_captcha(await page.content(), await page.title())

        await self._select_one_way(page)
        origin_evidence = await self._select_airport(page, "From", origin)
        destination_evidence = await self._select_airport(page, "To", destination)
        await self._select_departure_date(page, departure_date)

        form_state = await self._current_search_form_state(
            page,
            origin_evidence=origin_evidence,
            destination_evidence=destination_evidence,
            departure_date=departure_date,
        )
        if not form_state.is_ready:
            raise SpiceJetSearchInteractionError(
                FORM_STATE_NOT_READY,
                (
                    "SpiceJet form was not ready before search "
                    f"(origin={form_state.origin_committed}, destination={form_state.destination_committed}, "
                    f"date={form_state.departure_date_committed}, one_way={form_state.one_way_selected}, "
                    f"adult_count={form_state.adult_count}, currency={form_state.currency}, "
                    f"enabled={form_state.search_enabled}, validation_error={form_state.validation_error_visible}, "
                    f"page_ready={form_state.page_ready})"
                ),
            )
        return form_state

    async def _current_search_form_state(
        self,
        page,
        origin_evidence: SpiceJetSelectionEvidence,
        destination_evidence: SpiceJetSelectionEvidence,
        departure_date: date,
    ) -> SpiceJetSearchFormState:
        button_state = await self._search_button_state(page)
        body_text = await page.locator("body").inner_text(timeout=5000)
        return SpiceJetSearchFormState(
            origin_committed=self.selection_is_confirmed(origin_evidence),
            destination_committed=self.selection_is_confirmed(destination_evidence),
            departure_date_committed=self._selected_date_label(departure_date) in body_text,
            one_way_selected=await self._one_way_selected(page, body_text),
            adult_count=self._adult_count_from_text(body_text),
            currency=self._currency_from_text(body_text),
            search_enabled=button_state["enabled"],
            validation_error_visible=await self._validation_error_visible(page),
            page_ready=await page.evaluate("document.readyState === 'complete' || document.readyState === 'interactive'"),
            button_text=button_state["text"],
            button_attributes=button_state["attributes"],
        )

    async def _submit_search_attempt(self, page, attempt_number: int) -> SpiceJetSearchOutcome:
        request_statuses: list[int] = []
        request_failures: list[str] = []

        def relevant_url(url: str) -> bool:
            return "/search" in url or "/api/v" in url or "availability" in url or "lowfare" in url

        def on_response(response) -> None:
            url = response.url
            if relevant_url(url):
                request_statuses.append(response.status)

        def on_request_failed(request) -> None:
            url = request.url
            if relevant_url(url):
                failure = getattr(request, "failure", "")
                if callable(failure):
                    failure = failure()
                request_failures.append(f"{request.method} {url} {failure}")

        if hasattr(page, "on"):
            page.on("response", on_response)
            page.on("requestfailed", on_request_failed)

        try:
            await self._submit_search_once(page)
            logger.info("SpiceJet search clicked", extra={"event": "spicejet_search_clicked", "attempt": attempt_number})
            outcome = await self._monitor_search_after_click(page)
        finally:
            if hasattr(page, "remove_listener"):
                page.remove_listener("response", on_response)
                page.remove_listener("requestfailed", on_request_failed)

        blocked_statuses = [status for status in request_statuses if status in (403, 429)]
        if blocked_statuses:
            status = blocked_statuses[0]
            logger.warning(
                "SpiceJet search blocked by HTTP status",
                extra={"event": "spicejet_block_detected", "status": status, "attempt": attempt_number},
            )
            raise ScrapingBlockedException(f"SpiceJet search blocked with HTTP {status}")

        if outcome.succeeded:
            logger.info(
                "SpiceJet navigation detected",
                extra={"event": "spicejet_navigation_detected", "attempt": attempt_number, "final_url": outcome.final_url},
            )

        return SpiceJetSearchOutcome(
            classification=outcome.classification,
            final_url=outcome.final_url,
            navigation_detected=outcome.navigation_detected,
            results_rendered=outcome.results_rendered,
            flight_card_count=outcome.flight_card_count,
            visible_error=outcome.visible_error,
            request_statuses=tuple(request_statuses),
            request_failures=tuple(request_failures),
        )

    async def _reestablish_homepage_for_recovery(self, page) -> None:
        if getattr(page, "url", "").rstrip("/") != SPICEJET_HOME_URL.rstrip("/"):
            response = await page.goto(
                SPICEJET_HOME_URL,
                wait_until="domcontentloaded",
                timeout=int(self.config.timeout_seconds * 1000),
            )
            if response is not None and response.status in (403, 429):
                raise ScrapingBlockedException(f"HTTP {response.status} from SpiceJet during recovery")
        else:
            await page.reload(wait_until="domcontentloaded", timeout=int(self.config.timeout_seconds * 1000))
        await self._wait_for_homepage(page)

    async def _wait_for_homepage(self, page) -> None:
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeoutError:
            logger.info("SpiceJet homepage did not reach networkidle; continuing with rendered DOM")
        await self._airport_input_handle(page, "From")
        await self._airport_input_handle(page, "To")

    async def _select_one_way(self, page) -> None:
        one_way = page.get_by_text("One Way", exact=True)
        if await one_way.count():
            await one_way.first.click(timeout=int(self.config.timeout_seconds * 1000))
            await page.wait_for_timeout(300)

    async def _select_airport(self, page, field_label: str, airport_code: str) -> SpiceJetSelectionEvidence:
        target = airport_code.upper()
        input_handle = await self._airport_input_handle(page, field_label)
        await input_handle.click(timeout=int(self.config.timeout_seconds * 1000))
        await page.wait_for_timeout(500)

        option = await self._find_airport_option(page, target)
        if option is None:
            await input_handle.click(timeout=int(self.config.timeout_seconds * 1000))
            await input_handle.press("Control+A")
            await input_handle.type(target, delay=80)
            await page.wait_for_timeout(600)
            option = await self._find_airport_option(page, target)

        if option is None:
            raise RouteUnavailableException(f"SpiceJet airport option {target} was not visible for {field_label}")

        await self._click_airport_option(page, option)
        await page.wait_for_timeout(500)

        evidence = await self._selection_evidence(page, field_label, target, option_clicked=True)
        if not self.selection_is_confirmed(evidence):
            raise RouteUnavailableException(f"SpiceJet airport option {target} was not confirmed for {field_label}")
        return evidence

    async def _airport_input_handle(self, page, field_label: str):
        index = 0 if field_label.lower() == "from" else 1
        handle = await page.evaluate_handle(
            """
            ({ index }) => {
              const isVisible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 &&
                  style.visibility !== 'hidden' && style.display !== 'none';
              };
              const inputs = Array.from(document.querySelectorAll('input[type="text"]'))
                .filter(isVisible)
                .map((el) => ({ el, rect: el.getBoundingClientRect() }))
                .filter(({ rect }) => rect.y > 150 && rect.y < 360)
                .sort((a, b) => (a.rect.y - b.rect.y) || (a.rect.x - b.rect.x));
              return inputs[index] ? inputs[index].el : null;
            }
            """,
            {"index": index},
        )
        element = handle.as_element()
        if element is None:
            raise RouteUnavailableException(f"SpiceJet {field_label} airport input was not visible")
        return element

    async def _find_airport_option(self, page, airport_code: str) -> Optional[SpiceJetAirportOption]:
        city = AIRPORT_CITY_LABELS.get(airport_code, "")
        candidate = await page.evaluate(
            """
            ({ airportCode, city }) => {
              const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
              const isVisible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 &&
                  style.visibility !== 'hidden' && style.display !== 'none';
              };
              const exactCode = new RegExp('\\\\b' + airportCode + '\\\\b', 'i');
              const candidates = Array.from(document.querySelectorAll('div'))
                .map((el) => ({ el, text: normalize(el.innerText), rect: el.getBoundingClientRect() }))
                .filter(({ el, text, rect }) =>
                  isVisible(el) &&
                  exactCode.test(text) &&
                  new RegExp('\\\\b' + airportCode + '$', 'i').test(text) &&
                  (!city || text.toLowerCase().includes(city.toLowerCase())) &&
                  text.length <= 100 &&
                  rect.width >= 200 &&
                  rect.height >= 30
                )
                .map(({ el, text, rect }) => {
                  const endsWithCode = new RegExp('\\\\b' + airportCode + '$', 'i').test(text);
                  const rowLike = rect.width >= 250 && rect.height >= 35;
                  const score = (endsWithCode ? 100 : 0) + (rowLike ? 50 : 0) - text.length / 100;
                  return { el, text, score };
                })
                .sort((a, b) => b.score - a.score);
              if (!candidates.length) return null;
              const selected = candidates[0];
              selected.el.scrollIntoView({ block: 'center', inline: 'center' });
              const rect = selected.el.getBoundingClientRect();
              return {
                airport_code: airportCode,
                city,
                text: selected.text,
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height
              };
            }
            """,
            {"airportCode": airport_code, "city": city},
        )
        if candidate is None:
            return None
        return SpiceJetAirportOption(**candidate)

    async def _click_airport_option(self, page, option: SpiceJetAirportOption) -> None:
        await page.mouse.click(option.x + option.width / 2, option.y + option.height / 2)

    async def _selection_evidence(
        self,
        page,
        field_label: str,
        airport_code: str,
        option_clicked: bool,
    ) -> SpiceJetSelectionEvidence:
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(300)
        input_handle = await self._airport_input_handle(page, field_label)
        field_text = await self._element_text(input_handle)
        await page.mouse.click(15, 15)
        await page.wait_for_timeout(300)
        retained_text = await self._element_text(input_handle)
        autocomplete_open = await self._airport_option_visible(page, airport_code)
        validation_error = await self._validation_error_visible(page)
        return SpiceJetSelectionEvidence(
            field_label=field_label,
            airport_code=airport_code.upper(),
            field_text=retained_text or field_text,
            option_clicked=option_clicked,
            retained_after_blur=bool(retained_text and retained_text == field_text),
            autocomplete_open=autocomplete_open,
            validation_error_visible=validation_error,
        )

    @staticmethod
    async def _element_text(element) -> str:
        return await element.evaluate("(el) => (el.value || el.innerText || el.textContent || '').trim()")

    async def _airport_option_visible(self, page, airport_code: str) -> bool:
        option = await self._find_airport_option(page, airport_code)
        return option is not None

    async def _validation_error_visible(self, page) -> bool:
        body = await page.locator("body").inner_text(timeout=5000)
        lower = body.lower()
        return any(
            message in lower
            for message in (
                "select destination",
                "select origin",
                "please select",
                "invalid destination",
                "invalid origin",
            )
        )

    async def _select_departure_date(self, page, departure_date: date) -> None:
        await page.get_by_text("Departure Date", exact=True).first.click(timeout=int(self.config.timeout_seconds * 1000))
        await page.wait_for_timeout(500)

        month_label = f"{MONTH_NAMES[departure_date.month]} {departure_date.year}"
        await page.get_by_text(month_label, exact=True).first.wait_for(timeout=int(self.config.timeout_seconds * 1000))
        day_box = await page.evaluate(
            """
            ({ monthLabel, day }) => {
              const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
              const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 &&
                  style.visibility !== 'hidden' && style.display !== 'none';
              };
              const month = Array.from(document.querySelectorAll('div'))
                .map((el) => ({ el, text: normalize(el.innerText), rect: el.getBoundingClientRect() }))
                .filter(({ el, text }) => visible(el) && text === monthLabel)
                .sort((a, b) => (a.rect.y - b.rect.y) || (a.rect.x - b.rect.x))[0];
              if (!month) return null;
              const days = Array.from(document.querySelectorAll('div'))
                .map((el) => ({ el, text: normalize(el.innerText), rect: el.getBoundingClientRect() }))
                .filter(({ el, text, rect }) =>
                  visible(el) &&
                  text === String(day) &&
                  rect.y > month.rect.y &&
                  rect.y < month.rect.y + 360 &&
                  Math.abs(rect.x - month.rect.x) < 320 &&
                  rect.width >= 18 &&
                  rect.width <= 70 &&
                  rect.height >= 18 &&
                  rect.height <= 70
                )
                .sort((a, b) => (a.rect.y - b.rect.y) || (a.rect.x - b.rect.x));
              if (!days.length) return null;
              const selected = days[0];
              const rect = selected.rect;
              return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
            }
            """,
            {"monthLabel": month_label, "day": departure_date.day},
        )
        if day_box is None:
            raise RouteUnavailableException(f"SpiceJet date {departure_date.isoformat()} was not selectable")
        await page.mouse.click(day_box["x"] + day_box["width"] / 2, day_box["y"] + day_box["height"] / 2)
        await page.wait_for_timeout(500)

        expected_label = self._selected_date_label(departure_date)
        body_text = await page.locator("body").inner_text(timeout=5000)
        if expected_label not in body_text:
            raise RouteUnavailableException(f"SpiceJet date {departure_date.isoformat()} was not retained")

    async def _submit_search_once(self, page) -> None:
        button_state = await self._search_button_state(page)
        if not button_state["enabled"]:
            raise SpiceJetSearchInteractionError(FORM_STATE_NOT_READY, "SpiceJet search button was disabled before click")
        search = page.locator('[data-testid="home-page-flight-cta"]')
        if await search.count() == 0:
            search = page.get_by_text("Search Flight", exact=True)
        if await search.count() == 0:
            raise RouteUnavailableException("SpiceJet search button was not visible")
        await search.first.click(timeout=int(self.config.timeout_seconds * 1000))

    async def _monitor_search_after_click(self, page) -> SpiceJetSearchOutcome:
        deadline = monotonic_time.monotonic() + min(self.config.timeout_seconds, 25.0)
        start_url = getattr(page, "url", "")
        navigation_detected = False
        last_body = ""

        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except PlaywrightTimeoutError:
            logger.info("SpiceJet search did not reach networkidle; inspecting current DOM")

        while monotonic_time.monotonic() < deadline:
            title = await page.title()
            content = await page.content()
            self.detect_block_or_captcha(content, title)

            current_url = getattr(page, "url", "")
            navigation_detected = navigation_detected or current_url != start_url or "/search" in current_url
            try:
                last_body = await page.locator("body").inner_text(timeout=1000)
            except PlaywrightTimeoutError:
                last_body = ""

            visible_error = self._visible_search_error_from_text(last_body)
            if visible_error and "/search" not in current_url:
                return SpiceJetSearchOutcome(
                    classification=CLIENT_SIDE_VALIDATION,
                    final_url=current_url,
                    navigation_detected=navigation_detected,
                    results_rendered=False,
                    visible_error=visible_error,
                )

            if "/search" in current_url:
                results_rendered = await self._search_results_rendered(page, last_body)
                if results_rendered:
                    card_count = await self._count_visible_flight_cards(page, last_body)
                    return SpiceJetSearchOutcome(
                        classification=SEARCH_SUCCESS,
                        final_url=current_url,
                        navigation_detected=True,
                        results_rendered=True,
                        flight_card_count=card_count,
                    )

            await page.wait_for_timeout(500)

        final_url = getattr(page, "url", "")
        if "/search" in final_url:
            return SpiceJetSearchOutcome(
                classification=SEARCH_RESULTS_UI_MISSING,
                final_url=final_url,
                navigation_detected=True,
                results_rendered=False,
            )
        if navigation_detected:
            return SpiceJetSearchOutcome(
                classification=SEARCH_NAVIGATION_TIMEOUT,
                final_url=final_url,
                navigation_detected=True,
                results_rendered=False,
            )
        return SpiceJetSearchOutcome(
            classification=SEARCH_INTERACTION_TRANSIENT_FAILURE,
            final_url=final_url,
            navigation_detected=False,
            results_rendered=False,
        )

    async def _search_button_state(self, page) -> dict[str, Any]:
        state = await page.evaluate(
            """
            () => {
              const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
              const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 &&
                  style.visibility !== 'hidden' && style.display !== 'none';
              };
              const button = Array.from(document.querySelectorAll('[data-testid="home-page-flight-cta"], div'))
                .filter((el) => visible(el) && normalize(el.innerText) === 'Search Flight')
                .sort((a, b) => {
                  const aTest = a.getAttribute('data-testid') === 'home-page-flight-cta' ? 0 : 1;
                  const bTest = b.getAttribute('data-testid') === 'home-page-flight-cta' ? 0 : 1;
                  return aTest - bTest;
                })[0];
              if (!button) {
                return { enabled: false, text: '', attributes: {}, pointerEvents: '', opacity: '', cursor: '' };
              }
              const style = window.getComputedStyle(button);
              const attrs = {};
              for (const attr of button.attributes) attrs[attr.name] = attr.value;
              const disabled = button.hasAttribute('disabled') ||
                button.getAttribute('aria-disabled') === 'true' ||
                style.pointerEvents === 'none' ||
                Number(style.opacity || '1') < 0.5;
              return {
                enabled: !disabled,
                text: normalize(button.innerText),
                attributes: attrs,
                pointerEvents: style.pointerEvents,
                opacity: style.opacity,
                cursor: style.cursor
              };
            }
            """
        )
        return {
            "enabled": bool(state.get("enabled")),
            "text": state.get("text") or "",
            "attributes": state.get("attributes") or {},
            "pointerEvents": state.get("pointerEvents") or "",
            "opacity": state.get("opacity") or "",
            "cursor": state.get("cursor") or "",
        }

    async def _one_way_selected(self, page, body_text: str) -> bool:
        selected = await page.evaluate(
            """
            () => {
              const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
              const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 &&
                  style.visibility !== 'hidden' && style.display !== 'none';
              };
              const labels = Array.from(document.querySelectorAll('div'))
                .filter((el) => visible(el) && ['One Way', 'Round Trip'].includes(normalize(el.innerText)))
                .map((el) => {
                  let node = el;
                  const hints = [];
                  for (let i = 0; i < 4 && node; i += 1) {
                    const style = window.getComputedStyle(node);
                    hints.push([
                      node.getAttribute('aria-selected'),
                      node.getAttribute('aria-checked'),
                      node.getAttribute('data-testid'),
                      style.backgroundColor,
                      style.borderColor,
                      style.color
                    ].join('|'));
                    node = node.parentElement;
                  }
                  return { text: normalize(el.innerText), hints: hints.join(' ') };
                });
              const oneWay = labels.find((item) => item.text === 'One Way');
              const roundTrip = labels.find((item) => item.text === 'Round Trip');
              return {
                oneWayVisible: Boolean(oneWay),
                roundTripVisible: Boolean(roundTrip),
                oneWayHints: oneWay ? oneWay.hints : '',
                roundTripHints: roundTrip ? roundTrip.hints : ''
              };
            }
            """
        )
        one_way_hints = (selected.get("oneWayHints") or "").lower()
        round_trip_hints = (selected.get("roundTripHints") or "").lower()
        explicit_one_way = "true" in one_way_hints and "true" not in round_trip_hints
        return bool(explicit_one_way or ("One Way" in body_text and "Round Trip" in body_text))

    @staticmethod
    def _adult_count_from_text(body_text: str) -> int:
        match = re.search(r"\bPassengers\s+([0-9]+)\s+Adult\b|\b([0-9]+)\s+Adult\b", body_text, flags=re.IGNORECASE)
        if not match:
            return 0
        return int(match.group(1) or match.group(2))

    @staticmethod
    def _currency_from_text(body_text: str) -> str:
        match = re.search(r"\bCurrency\s+([A-Z]{3})\b|\b(INR)\b", body_text, flags=re.IGNORECASE)
        return (match.group(1) or match.group(2)).upper() if match else ""

    async def _search_results_rendered(self, page, body_text: Optional[str] = None) -> bool:
        text = body_text
        if text is None:
            text = await page.locator("body").inner_text(timeout=5000)

        result_section = page.locator("#list-results-section-0")
        if await result_section.count():
            return True

        if await self._count_visible_flight_cards(page, text):
            return True

        lower = text.lower()
        return (
            "/search" in getattr(page, "url", "")
            and ("select your departure" in lower or "select flight" in lower)
            and any(token in lower for token in ("departs", "fares", "sold out", "no flights"))
        )

    @staticmethod
    def _visible_search_error_from_text(body_text: str) -> Optional[str]:
        lower = body_text.lower()
        for message in (
            "select destination",
            "select origin",
            "please select",
            "invalid destination",
            "invalid origin",
            "unable to process",
            "something went wrong",
        ):
            if message in lower:
                return message
        return None

    async def _result_page_text(self, page) -> str:
        result_section = page.locator("#list-results-section-0")
        if await result_section.count():
            return await result_section.first.inner_text(timeout=15000)
        return await page.locator("body").inner_text(timeout=15000)

    @staticmethod
    async def _count_visible_flight_cards(page, body_text: str) -> int:
        locator_count = await page.locator("text=/\\bSG\\s?\\d{2,4}\\b/i").count()
        if locator_count:
            return locator_count
        return len(set(re.findall(r"\bSG\s?\d{2,4}\b", body_text, flags=re.IGNORECASE)))

    @staticmethod
    def _looks_like_result_state(url: str, body_text: str) -> bool:
        lower = body_text.lower()
        return (
            url.rstrip("/") != SPICEJET_HOME_URL.rstrip("/")
            or bool(re.search(r"\bSG\s?\d{2,4}\b", body_text, flags=re.IGNORECASE))
            or any(token in lower for token in ("select flight", "flight details", "no flights", "sold out"))
        )

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
        """Parse visible SpiceJet result rows into raw quote schemas."""
        lines = cls._visible_lines(rendered_text)
        visible_departure_date = cls._parse_selected_departure_date(lines)
        if visible_departure_date != departure_date:
            return []

        target_origin = origin.upper()
        target_destination = destination.upper()
        advance_window_days = resolve_advance_window_days(
            visible_departure_date,
            collected_at,
            requested_advance_window_days,
        )
        quotes: List[RawAirfareQuoteCreate] = []

        for parsed in cls._parse_visible_flights(lines, target_origin, target_destination):
            arrival_date = visible_departure_date + timedelta(days=1 if parsed.arrival_next_day else 0)
            quotes.append(
                RawAirfareQuoteCreate(
                    source_id=source_id,
                    route_id=route_id,
                    flight_number=parsed.flight_number,
                    departure_datetime=datetime.combine(visible_departure_date, parsed.departure_time, tzinfo=timezone.utc),
                    arrival_datetime=datetime.combine(arrival_date, parsed.arrival_time, tzinfo=timezone.utc),
                    advance_window_days=advance_window_days,
                    base_fare=0.0,
                    taxes_fees=0.0,
                    total_fare=round(parsed.total_fare, 2),
                    cabin_class=cls._cabin_value(cabin_class, parsed.fare_family),
                    scraped_at=collected_at,
                )
            )
        return quotes

    @classmethod
    def _parse_visible_flights(
        cls,
        lines: Sequence[str],
        target_origin: str,
        target_destination: str,
    ) -> List[SpiceJetParsedFlight]:
        result_lines = cls._result_lines(lines)
        fare_families = cls._fare_families(result_lines)
        if not fare_families:
            return []

        flights: List[SpiceJetParsedFlight] = []
        flight_indexes = [
            idx for idx, line in enumerate(result_lines)
            if re.fullmatch(r"SG\s?\d{2,4}", line, flags=re.IGNORECASE)
        ]
        for idx in flight_indexes:
            route = cls._route_before_flight(result_lines, idx, target_origin, target_destination)
            if route is None:
                continue

            departure_time, arrival_time, arrival_next_day = route
            fares = cls._fares_after_flight(result_lines, idx, fare_families)
            for fare_family, amount in fares:
                flights.append(
                    SpiceJetParsedFlight(
                        flight_number=cls._normalize_flight_number(result_lines[idx]),
                        origin=target_origin,
                        destination=target_destination,
                        departure_time=departure_time,
                        arrival_time=arrival_time,
                        arrival_next_day=arrival_next_day,
                        fare_family=fare_family,
                        total_fare=amount,
                    )
                )

        return flights

    @staticmethod
    def _result_lines(lines: Sequence[str]) -> List[str]:
        try:
            start = lines.index("DEPARTS")
        except ValueError:
            start = 0

        end = len(lines)
        for marker in ("Direct flight", "About Us", "SpiceSaver Fare"):
            try:
                end = min(end, lines.index(marker, start))
            except ValueError:
                continue
        return list(lines[start:end])

    @staticmethod
    def _fare_families(lines: Sequence[str]) -> List[str]:
        families = []
        for family in ("SpiceSaver", "SpiceFlex", "SpiceMax"):
            if family in lines:
                families.append(family)
        return families

    @classmethod
    def _route_before_flight(
        cls,
        lines: Sequence[str],
        flight_idx: int,
        target_origin: str,
        target_destination: str,
    ) -> Optional[tuple[time, time, bool]]:
        destination_idx = cls._nearest_exact_token_before(lines, target_destination, flight_idx)
        if destination_idx is None:
            return None

        arrival_time_idx, arrival_raw = cls._nearest_time_before(lines, destination_idx)
        if arrival_time_idx is None or arrival_raw is None:
            return None

        origin_idx = cls._nearest_exact_token_before(lines, target_origin, arrival_time_idx)
        if origin_idx is None:
            return None

        departure_time_idx, departure_raw = cls._nearest_time_before(lines, origin_idx)
        if departure_time_idx is None or departure_raw is None:
            return None

        departure_time = cls._parse_clock_time(departure_raw)
        arrival_time = cls._parse_clock_time(arrival_raw)
        if departure_time is None or arrival_time is None:
            return None
        return departure_time, arrival_time, "+1" in arrival_raw

    @staticmethod
    def _nearest_exact_token_before(lines: Sequence[str], token: str, before_idx: int) -> Optional[int]:
        for idx in range(before_idx - 1, -1, -1):
            if lines[idx].upper() == token.upper():
                return idx
        return None

    @staticmethod
    def _nearest_time_before(lines: Sequence[str], before_idx: int) -> tuple[Optional[int], Optional[str]]:
        for idx in range(before_idx - 1, -1, -1):
            if re.fullmatch(r"\d{1,2}:\d{2}(?:\+1)?", lines[idx]):
                return idx, lines[idx]
        return None, None

    @classmethod
    def _fares_after_flight(
        cls,
        lines: Sequence[str],
        flight_idx: int,
        fare_families: Sequence[str],
    ) -> List[tuple[str, float]]:
        fares: List[tuple[str, float]] = []
        next_flight_idx = len(lines)
        for idx in range(flight_idx + 1, len(lines)):
            if re.fullmatch(r"SG\s?\d{2,4}", lines[idx], flags=re.IGNORECASE):
                next_flight_idx = idx
                break

        search_window = lines[flight_idx + 1 : next_flight_idx]
        for amount in cls._money_values(search_window):
            if len(fares) >= len(fare_families):
                break
            fares.append((fare_families[len(fares)], amount))
        return fares

    @staticmethod
    def _money_values(lines: Sequence[str]) -> List[float]:
        values: List[float] = []
        currency_markers = {"₹", "â‚¹", "INR", "Rs", "Rs."}
        for idx, line in enumerate(lines):
            amount = SpiceJetWebsiteScraper.parse_money(line)
            if amount is not None:
                values.append(amount)
                continue

            if line in currency_markers and idx + 1 < len(lines):
                next_line = lines[idx + 1]
                if re.fullmatch(r"[0-9][0-9,]*(?:\.[0-9]+)?", next_line):
                    values.append(float(next_line.replace(",", "")))
        return values

    @staticmethod
    def parse_money(value: str) -> Optional[float]:
        normalized = SpiceJetWebsiteScraper._normalize(value).replace("\u00a0", " ")
        match = re.search(
            r"(?:INR|Rs\.?|₹|â‚¹)\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
            normalized,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        return float(match.group(1).replace(",", ""))

    @staticmethod
    def _parse_selected_departure_date(lines: Sequence[str]) -> Optional[date]:
        for line in lines[:80]:
            match = re.search(
                r"(?:Depart Date\s*:\s*)?([A-Z][a-z]{2}),\s*([0-9]{1,2})\s+([A-Z][a-z]{2})\s+([0-9]{4})",
                line,
            )
            if not match:
                continue
            candidate = f"{match.group(1)}, {int(match.group(2)):02d} {match.group(3)} {match.group(4)}"
            try:
                return datetime.strptime(candidate, "%a, %d %b %Y").date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_clock_time(value: str) -> Optional[time]:
        match = re.fullmatch(r"(\d{1,2}):(\d{2})(?:\+1)?", value)
        if not match:
            return None
        hour = int(match.group(1))
        minute = int(match.group(2))
        if hour > 23 or minute > 59:
            return None
        return time(hour, minute)

    @staticmethod
    def _normalize_flight_number(value: str) -> str:
        match = re.fullmatch(r"SG\s?(\d{2,4})", value.strip(), flags=re.IGNORECASE)
        if not match:
            return value.strip().upper()
        return f"SG {match.group(1)}"

    @staticmethod
    def selection_is_confirmed(evidence: SpiceJetSelectionEvidence) -> bool:
        expected_city = AIRPORT_CITY_LABELS.get(evidence.airport_code, "")
        expected_text = f"{expected_city} ({evidence.airport_code})" if expected_city else evidence.airport_code
        return (
            SpiceJetWebsiteScraper._normalize(evidence.field_text) == expected_text
            and evidence.option_clicked
            and evidence.retained_after_blur
            and not evidence.autocomplete_open
            and not evidence.validation_error_visible
        )

    @staticmethod
    def airport_option_score(text: str, airport_code: str) -> float:
        normalized = SpiceJetWebsiteScraper._normalize(text)
        code = airport_code.upper()
        city = AIRPORT_CITY_LABELS.get(code, "")
        if not re.search(rf"\b{re.escape(code)}\b", normalized):
            return -1.0
        score = 0.0
        if city and city.lower() in normalized.lower():
            score += 50.0
        if re.search(rf"\b{re.escape(code)}$", normalized):
            score += 100.0
        if len(normalized) <= 100:
            score += 10.0
        return score

    @staticmethod
    def _selected_date_label(departure_date: date) -> str:
        weekday = departure_date.strftime("%a")
        month = departure_date.strftime("%b")
        return f"{weekday}, {departure_date.day} {month} {departure_date.year}"

    @staticmethod
    def _visible_lines(rendered_text: str) -> List[str]:
        return [
            re.sub(r"\s+", " ", raw_line).strip()
            for raw_line in rendered_text.splitlines()
            if re.sub(r"\s+", " ", raw_line).strip()
        ]

    @staticmethod
    def _cabin_value(cabin_class: str, fare_family: str) -> str:
        value = f"{cabin_class.upper()}-{fare_family.upper()}"
        return value[:30]

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value or "").strip()
