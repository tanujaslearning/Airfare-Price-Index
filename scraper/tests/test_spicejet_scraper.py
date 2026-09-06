"""Tests for SpiceJet interaction and result parsing without live website access."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import scraper.airlines.spicejet_scraper as spicejet_module
from scraper.airlines.spicejet_scraper import (
    CAPTCHA_DETECTED,
    SEARCH_INTERACTION_TRANSIENT_FAILURE,
    SEARCH_NAVIGATION_TIMEOUT,
    SEARCH_RESULTS_UI_MISSING,
    SEARCH_SUCCESS,
    SpiceJetSearchFormState,
    SpiceJetSearchInteractionError,
    SpiceJetSearchOutcome,
    SpiceJetSelectionEvidence,
    SpiceJetWebsiteScraper,
)
from scraper.base.base_scraper import CaptchaDetectedException, ScrapingBlockedException

FIXTURE_TEXT = Path("diagnostics/spicejet_postclick_2026-09-05/visible_text.txt").read_text(encoding="utf-8")


def _collect(rendered_text: str = FIXTURE_TEXT, departure: date = date(2026, 9, 5)):
    return SpiceJetWebsiteScraper.extract_quotes_from_text(
        rendered_text,
        origin="DEL",
        destination="BOM",
        departure_date=departure,
        route_id=1,
        source_id=3,
        cabin_class="ECONOMY",
        collected_at=datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc),
    )


def _collect_with_requested_window(window: int):
    departure = date(2026, 9, 4) + timedelta(days=window)
    header_date = departure.strftime("%a, %d %b %Y")
    text = _result_text(
        route_line=f"One Way : Delhi to MumbaiDepart Date : {header_date}Passengers : 1 Adult",
        header_date=header_date,
    )
    return SpiceJetWebsiteScraper.extract_quotes_from_text(
        text,
        origin="DEL",
        destination="BOM",
        departure_date=departure,
        route_id=1,
        source_id=3,
        cabin_class="ECONOMY",
        collected_at=datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc),
        requested_advance_window_days=window,
    )


def _result_text(
    route_line: str = "One Way : Delhi to MumbaiDepart Date : Sat, 05 Sep 2026Passengers : 1 Adult",
    header_date: str = "Sat, 05 Sep 2026",
    origin: str = "DEL",
    destination: str = "BOM",
    departure_time: str = "22:30",
    arrival_time: str = "00:50+1",
    fare_lines: str = """
₹ 18,047
Earn 636
Points
₹ 18,467
Earn 652
Points
₹ 19,359
Earn 684
Points
""",
):
    return f"""
Login
Signup
{route_line}
Select your Departure to Mumbai
{header_date}
Filter By
All Flights
Direct
DEPARTS
DURATION
ARRIVES
Compare Fares
SpiceSaver
SpiceFlex
SpiceMax
{departure_time}
{origin}
Flight Details
2h 20m
{arrival_time}
{destination}
SG 802
Direct
{fare_lines}
Direct flight
Hopping flight (same aircraft)
All the fare include taxes and fee.
"""


def _ready_form_state() -> SpiceJetSearchFormState:
    return SpiceJetSearchFormState(
        origin_committed=True,
        destination_committed=True,
        departure_date_committed=True,
        one_way_selected=True,
        adult_count=1,
        currency="INR",
        search_enabled=True,
        validation_error_visible=False,
        page_ready=True,
        button_text="Search Flight",
        button_attributes={"data-testid": "home-page-flight-cta"},
    )


def _success_outcome() -> SpiceJetSearchOutcome:
    return SpiceJetSearchOutcome(
        classification=SEARCH_SUCCESS,
        final_url="https://www.spicejet.com/search?from=DEL&to=BOM&tripType=1&departure=2026-09-05&adult=1&child=0&srCitizen=0&infant=0&currency=INR&redirectTo=/",
        navigation_detected=True,
        results_rendered=True,
        flight_card_count=1,
        request_statuses=(200, 200),
    )


def _failure_outcome(classification: str, final_url: str = "https://www.spicejet.com/") -> SpiceJetSearchOutcome:
    return SpiceJetSearchOutcome(
        classification=classification,
        final_url=final_url,
        navigation_detected=final_url != "https://www.spicejet.com/",
        results_rendered=False,
    )


class DummyPage:
    def __init__(self):
        self.url = "https://www.spicejet.com/"
        self.responses = []
        self.request_failures = []

    def on(self, event, callback):
        if event == "response":
            for response in self.responses:
                callback(response)
        if event == "requestfailed":
            for request in self.request_failures:
                callback(request)

    def remove_listener(self, event, callback):
        return None


class DummyResponse:
    def __init__(self, status: int, url: str = "https://www.spicejet.com/api/v3/search/availability"):
        self.status = status
        self.url = url


class StateMachineHarness(SpiceJetWebsiteScraper):
    def __init__(self, outcomes=None, monitor_exception=None):
        super().__init__()
        self.outcomes = list(outcomes or [])
        self.monitor_exception = monitor_exception
        self.prepares = 0
        self.clicks = 0
        self.recoveries = 0

    async def _prepare_and_verify_search_form(self, page, origin, destination, departure_date):
        self.prepares += 1
        return _ready_form_state()

    async def _submit_search_once(self, page):
        self.clicks += 1

    async def _monitor_search_after_click(self, page):
        if self.monitor_exception:
            raise self.monitor_exception
        outcome = self.outcomes.pop(0)
        page.url = outcome.final_url
        return outcome

    async def _reestablish_homepage_for_recovery(self, page):
        self.recoveries += 1
        page.url = "https://www.spicejet.com/"


class FakePlaywrightManager:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeBrowser:
    async def close(self):
        return None


class FakeContext:
    def __init__(self, page):
        self.page = page

    async def new_page(self):
        return self.page

    async def close(self):
        return None


class FakeGotoResponse:
    status = 200


class FetchPage(DummyPage):
    async def goto(self, url, wait_until, timeout):
        self.url = url
        return FakeGotoResponse()

    async def content(self):
        return "<html>SpiceJet</html>"

    async def title(self):
        return "SpiceJet"


class FetchHarness(SpiceJetWebsiteScraper):
    def __init__(self, interaction_exception=None):
        super().__init__()
        self.interaction_exception = interaction_exception
        self.interaction_called = False
        self.result_text_read = False

    async def verify_policy_and_rate_limit(self, target_url):
        return None

    async def create_browser_context(self, playwright):
        return FakeBrowser(), FakeContext(FetchPage())

    async def _wait_for_homepage(self, page):
        return None

    async def _run_search_interaction(self, page, origin, destination, departure_date):
        self.interaction_called = True
        if self.interaction_exception:
            raise self.interaction_exception
        page.url = _success_outcome().final_url
        return _success_outcome()

    async def _result_page_text(self, page):
        self.result_text_read = True
        return _result_text()


class FakeLocator:
    def __init__(self, count_value=0, text=""):
        self.count_value = count_value
        self.text = text

    async def count(self):
        return self.count_value

    async def inner_text(self, timeout=5000):
        return self.text


class ResultsRenderedPage:
    url = "https://www.spicejet.com/search?from=DEL&to=BOM"

    def locator(self, selector):
        if selector == "#list-results-section-0":
            return FakeLocator(count_value=1)
        return FakeLocator(count_value=0)


@pytest.mark.asyncio
async def test_spicejet_interaction_state_machine_normal_success():
    scraper = StateMachineHarness([_success_outcome()])
    outcome = await scraper._run_search_interaction(DummyPage(), "DEL", "BOM", date(2026, 9, 5))

    assert outcome.succeeded
    assert scraper.prepares == 1
    assert scraper.clicks == 1
    assert scraper.recoveries == 0


@pytest.mark.asyncio
async def test_spicejet_interaction_no_navigation_after_click_is_classified():
    scraper = StateMachineHarness([
        _failure_outcome(SEARCH_INTERACTION_TRANSIENT_FAILURE),
        _failure_outcome(SEARCH_INTERACTION_TRANSIENT_FAILURE),
    ])

    with pytest.raises(SpiceJetSearchInteractionError) as exc:
        await scraper._run_search_interaction(DummyPage(), "DEL", "BOM", date(2026, 9, 5))

    assert exc.value.classification == SEARCH_INTERACTION_TRANSIENT_FAILURE


@pytest.mark.asyncio
async def test_spicejet_interaction_bounded_recovery_success():
    scraper = StateMachineHarness([
        _failure_outcome(SEARCH_INTERACTION_TRANSIENT_FAILURE),
        _success_outcome(),
    ])
    outcome = await scraper._run_search_interaction(DummyPage(), "DEL", "BOM", date(2026, 9, 5))

    assert outcome.succeeded
    assert scraper.recoveries == 1
    assert scraper.clicks == 2


@pytest.mark.asyncio
async def test_spicejet_interaction_bounded_recovery_failure():
    scraper = StateMachineHarness([
        _failure_outcome(SEARCH_INTERACTION_TRANSIENT_FAILURE),
        _failure_outcome(SEARCH_INTERACTION_TRANSIENT_FAILURE),
    ])

    with pytest.raises(SpiceJetSearchInteractionError):
        await scraper._run_search_interaction(DummyPage(), "DEL", "BOM", date(2026, 9, 5))

    assert scraper.recoveries == 1
    assert scraper.clicks == 2


@pytest.mark.asyncio
async def test_spicejet_interaction_captcha_stops_immediately():
    scraper = StateMachineHarness(monitor_exception=CaptchaDetectedException(CAPTCHA_DETECTED))

    with pytest.raises(CaptchaDetectedException):
        await scraper._run_search_interaction(DummyPage(), "DEL", "BOM", date(2026, 9, 5))

    assert scraper.clicks == 1
    assert scraper.recoveries == 0


@pytest.mark.asyncio
async def test_spicejet_interaction_403_429_block_stops_immediately():
    scraper = StateMachineHarness([_success_outcome()])
    page = DummyPage()
    page.responses = [DummyResponse(429)]

    with pytest.raises(ScrapingBlockedException):
        await scraper._run_search_interaction(page, "DEL", "BOM", date(2026, 9, 5))

    assert scraper.clicks == 1
    assert scraper.recoveries == 0


@pytest.mark.asyncio
async def test_spicejet_interaction_navigation_timeout_classification():
    scraper = StateMachineHarness([
        _failure_outcome(SEARCH_NAVIGATION_TIMEOUT, "https://www.spicejet.com/intermediate"),
        _failure_outcome(SEARCH_NAVIGATION_TIMEOUT, "https://www.spicejet.com/intermediate"),
    ])

    with pytest.raises(SpiceJetSearchInteractionError) as exc:
        await scraper._run_search_interaction(DummyPage(), "DEL", "BOM", date(2026, 9, 5))

    assert exc.value.classification == SEARCH_NAVIGATION_TIMEOUT


@pytest.mark.asyncio
async def test_spicejet_interaction_results_url_reached_but_ui_missing():
    search_url = "https://www.spicejet.com/search?from=DEL&to=BOM"
    scraper = StateMachineHarness([
        _failure_outcome(SEARCH_RESULTS_UI_MISSING, search_url),
        _failure_outcome(SEARCH_RESULTS_UI_MISSING, search_url),
    ])

    with pytest.raises(SpiceJetSearchInteractionError) as exc:
        await scraper._run_search_interaction(DummyPage(), "DEL", "BOM", date(2026, 9, 5))

    assert exc.value.classification == SEARCH_RESULTS_UI_MISSING


@pytest.mark.asyncio
async def test_spicejet_successful_navigation_is_followed_by_parser(monkeypatch):
    monkeypatch.setattr(spicejet_module, "async_playwright", lambda: FakePlaywrightManager())
    scraper = FetchHarness()

    quotes = await scraper.fetch_quotes("DEL", "BOM", date(2026, 9, 5), source_id=3)

    assert scraper.interaction_called
    assert scraper.result_text_read
    assert {quote.flight_number for quote in quotes} == {"SG 802"}


@pytest.mark.asyncio
async def test_spicejet_live_failure_has_no_mock_fallback(monkeypatch):
    monkeypatch.setattr(spicejet_module, "async_playwright", lambda: FakePlaywrightManager())
    interaction_error = SpiceJetSearchInteractionError(
        SEARCH_INTERACTION_TRANSIENT_FAILURE,
        "public search stayed on homepage",
    )
    scraper = FetchHarness(interaction_exception=interaction_error)

    with pytest.raises(SpiceJetSearchInteractionError):
        await scraper.fetch_quotes("DEL", "BOM", date(2026, 9, 5), source_id=3)

    assert scraper.interaction_called
    assert not scraper.result_text_read


@pytest.mark.asyncio
async def test_spicejet_interaction_uses_exactly_one_initial_click():
    scraper = StateMachineHarness([_success_outcome()])

    await scraper._run_search_interaction(DummyPage(), "DEL", "BOM", date(2026, 9, 5))

    assert scraper.clicks == 1


@pytest.mark.asyncio
async def test_spicejet_interaction_uses_at_most_one_recovery_click():
    scraper = StateMachineHarness([
        _failure_outcome(SEARCH_INTERACTION_TRANSIENT_FAILURE),
        _failure_outcome(SEARCH_INTERACTION_TRANSIENT_FAILURE),
    ])

    with pytest.raises(SpiceJetSearchInteractionError):
        await scraper._run_search_interaction(DummyPage(), "DEL", "BOM", date(2026, 9, 5))

    assert scraper.clicks == 2
    assert scraper.recoveries == 1


@pytest.mark.asyncio
async def test_spicejet_successful_result_detection():
    scraper = SpiceJetWebsiteScraper()

    assert await scraper._search_results_rendered(ResultsRenderedPage(), "Select your Departure\nDEPARTS\nSG 802")


def test_spicejet_interaction_exception_exposes_clear_classification():
    exc = SpiceJetSearchInteractionError(SEARCH_RESULTS_UI_MISSING, "results UI did not render")

    assert exc.classification == SEARCH_RESULTS_UI_MISSING
    assert SEARCH_RESULTS_UI_MISSING in str(exc)


def test_spicejet_bom_autocomplete_confirmation_requires_option_click():
    evidence = SpiceJetSelectionEvidence(
        field_label="To",
        airport_code="BOM",
        field_text="Mumbai (BOM)",
        option_clicked=False,
        retained_after_blur=True,
        autocomplete_open=False,
        validation_error_visible=False,
    )

    assert not SpiceJetWebsiteScraper.selection_is_confirmed(evidence)


def test_spicejet_confirms_bom_after_explicit_option_selection():
    evidence = SpiceJetSelectionEvidence(
        field_label="To",
        airport_code="BOM",
        field_text="Mumbai (BOM)",
        option_clicked=True,
        retained_after_blur=True,
        autocomplete_open=False,
        validation_error_visible=False,
    )

    assert SpiceJetWebsiteScraper.selection_is_confirmed(evidence)


def test_spicejet_rejects_selection_when_autocomplete_remains_open():
    evidence = SpiceJetSelectionEvidence(
        field_label="To",
        airport_code="BOM",
        field_text="Mumbai (BOM)",
        option_clicked=True,
        retained_after_blur=True,
        autocomplete_open=True,
        validation_error_visible=False,
    )

    assert not SpiceJetWebsiteScraper.selection_is_confirmed(evidence)


def test_spicejet_origin_del_confirmation_remains_supported():
    evidence = SpiceJetSelectionEvidence(
        field_label="From",
        airport_code="DEL",
        field_text="Delhi (DEL)",
        option_clicked=True,
        retained_after_blur=True,
        autocomplete_open=False,
        validation_error_visible=False,
    )

    assert SpiceJetWebsiteScraper.selection_is_confirmed(evidence)


def test_spicejet_prefers_visible_city_airport_option_over_short_text():
    full_option = "Mumbai Chhatrapati Shivaji Maharaj International Airport BOM"
    short_text = "BOM"

    assert SpiceJetWebsiteScraper.airport_option_score(full_option, "BOM") > (
        SpiceJetWebsiteScraper.airport_option_score(short_text, "BOM")
    )


def test_spicejet_date_label_matches_existing_picker_display():
    assert SpiceJetWebsiteScraper._selected_date_label(date(2026, 9, 5)) == "Sat, 5 Sep 2026"


def test_spicejet_extracts_sg802_from_saved_fixture():
    quotes = _collect()

    assert {quote.flight_number for quote in quotes} == {"SG 802"}
    assert len(quotes) == 3


def test_spicejet_validates_del_bom_route():
    quotes = _collect()

    assert all(quote.route_id == 1 for quote in quotes)
    assert all(quote.source_id == 3 for quote in quotes)
    assert all(quote.flight_number == "SG 802" for quote in quotes)


def test_spicejet_extracts_departure_date_from_result_page():
    quote = _collect()[0]

    assert quote.departure_datetime.date() == date(2026, 9, 5)
    assert quote.advance_window_days == 1


@pytest.mark.parametrize("window", [1, 7, 15, 30, 45])
def test_spicejet_uses_requested_advance_window_context(window):
    quotes = _collect_with_requested_window(window)

    assert len(quotes) == 3
    assert {quote.advance_window_days for quote in quotes} == {window}


def test_spicejet_parser_does_not_silently_convert_actual_t0_to_t1():
    quotes = SpiceJetWebsiteScraper.extract_quotes_from_text(
        _result_text(),
        origin="DEL",
        destination="BOM",
        departure_date=date(2026, 9, 5),
        route_id=1,
        source_id=3,
        cabin_class="ECONOMY",
        collected_at=datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc),
    )

    assert len(quotes) == 3
    assert {quote.advance_window_days for quote in quotes} == {0}


def test_spicejet_parses_normal_same_day_arrival():
    quotes = _collect(_result_text(arrival_time="23:50"))

    assert quotes[0].arrival_datetime.isoformat() == "2026-09-05T23:50:00+00:00"


def test_spicejet_parses_next_day_arrival_marker():
    quotes = _collect()

    assert quotes[0].departure_datetime.isoformat() == "2026-09-05T22:30:00+00:00"
    assert quotes[0].arrival_datetime.isoformat() == "2026-09-06T00:50:00+00:00"


def test_spicejet_extracts_fare_families():
    quotes = _collect()

    assert [quote.cabin_class for quote in quotes] == [
        "ECONOMY-SPICESAVER",
        "ECONOMY-SPICEFLEX",
        "ECONOMY-SPICEMAX",
    ]


def test_spicejet_total_fare_parsing_variants():
    assert SpiceJetWebsiteScraper.parse_money("INR 18,047") == 18047.0
    assert SpiceJetWebsiteScraper.parse_money("₹ 18,467") == 18467.0
    assert SpiceJetWebsiteScraper.parse_money("â‚¹ 19,359") == 19359.0


def test_spicejet_extracts_multiple_fares_on_one_flight():
    quotes = _collect()

    assert [(quote.cabin_class, quote.total_fare) for quote in quotes] == [
        ("ECONOMY-SPICESAVER", 18047.0),
        ("ECONOMY-SPICEFLEX", 18467.0),
        ("ECONOMY-SPICEMAX", 19359.0),
    ]


def test_spicejet_fares_remain_associated_with_sg802():
    quotes = _collect()

    assert [(quote.flight_number, quote.cabin_class, quote.total_fare) for quote in quotes] == [
        ("SG 802", "ECONOMY-SPICESAVER", 18047.0),
        ("SG 802", "ECONOMY-SPICEFLEX", 18467.0),
        ("SG 802", "ECONOMY-SPICEMAX", 19359.0),
    ]


def test_spicejet_rejects_wrong_route():
    wrong_route_text = _result_text(origin="DEL", destination="NMI")

    assert _collect(wrong_route_text) == []


def test_spicejet_rejects_wrong_departure_date():
    wrong_date_text = _result_text(
        route_line="One Way : Delhi to MumbaiDepart Date : Sun, 06 Sep 2026Passengers : 1 Adult",
        header_date="Sun, 06 Sep 2026",
    )

    assert _collect(wrong_date_text) == []


def test_spicejet_parser_does_not_require_generated_css_classes():
    assert "css-" not in _result_text()
    assert "r-" not in _result_text()
    assert len(_collect(_result_text())) == 3


def test_spicejet_missing_fare_handling_skips_card():
    no_fare_text = _result_text(fare_lines="Earn 636\nPoints")

    assert _collect(no_fare_text) == []


def test_spicejet_malformed_time_handling_skips_card():
    bad_time_text = _result_text(arrival_time="24:90")

    assert _collect(bad_time_text) == []


def test_spicejet_malformed_fare_handling_skips_card():
    bad_fare_text = _result_text(fare_lines="INR TBD\nEarn 636\nPoints")

    assert _collect(bad_fare_text) == []


def test_spicejet_no_result_page_handling():
    assert _collect("No flights are available for this route") == []


def test_spicejet_multiple_visible_result_cards_do_not_leak_fares():
    second_card = """
08:00
DEL
Flight Details
2h 10m
10:10
BOM
SG 900
Direct
INR 6,000
INR 7,000
INR 8,000
"""
    text = _result_text().replace("\nDirect flight", second_card + "\nDirect flight")

    quotes = _collect(text)

    assert [(quote.flight_number, quote.total_fare) for quote in quotes] == [
        ("SG 802", 18047.0),
        ("SG 802", 18467.0),
        ("SG 802", 19359.0),
        ("SG 900", 6000.0),
        ("SG 900", 7000.0),
        ("SG 900", 8000.0),
    ]
