"""Read-only HappyFares feasibility diagnostic.

This script uses only the public browser UI, never imports ingestion services,
and opens apix.db read-only only for count verification.
"""

import asyncio
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import settings
from scraper.base.robots_checker import RobotsChecker, RobotsInconclusiveException


ARTIFACT_DIR = Path(__file__).resolve().parent
BOOKING_URL = "https://www.happyfares.in/"
ROBOTS_TARGETS = [
    BOOKING_URL,
    "https://www.happyfares.in/flights",
    "https://www.happyfares.in/flight-search",
]
WINDOWS = [1, 7, 15, 30, 45]
CAPTCHA_TERMS = ("captcha", "hcaptcha", "recaptcha", "turnstile", "verify you are human")
BLOCK_TERMS = ("access denied", "403 forbidden", "429", "too many requests", "blocked")


def db_counts() -> dict:
    con = sqlite3.connect("file:apix.db?mode=ro", uri=True)
    cur = con.cursor()
    queries = {
        "raw_total": "select count(*) from raw_airfare_quotes",
        "processed_total": "select count(*) from processed_airfare_quotes",
        "live_raw": "select count(*) from raw_airfare_quotes where collection_mode='LIVE'",
        "live_processed": (
            "select count(*) from processed_airfare_quotes "
            "join raw_airfare_quotes on raw_airfare_quotes.id=processed_airfare_quotes.raw_quote_id "
            "where raw_airfare_quotes.collection_mode='LIVE'"
        ),
        "mock_raw": "select count(*) from raw_airfare_quotes where collection_mode='MOCK'",
        "mock_processed": (
            "select count(*) from processed_airfare_quotes "
            "join raw_airfare_quotes on raw_airfare_quotes.id=processed_airfare_quotes.raw_quote_id "
            "where raw_airfare_quotes.collection_mode='MOCK'"
        ),
    }
    counts = {label: cur.execute(sql).fetchone()[0] for label, sql in queries.items()}
    con.close()
    return counts


async def robots_results() -> dict:
    checker = RobotsChecker(cache_ttl_seconds=0)
    results = {}
    for target in ROBOTS_TARGETS:
        started = datetime.now()
        try:
            allowed = await checker.is_allowed(target)
            parser = await checker.get_parser(target)
            _, robots_url = checker._get_robots_url(target)
            results[target] = {
                "robots_url": robots_url,
                "status": "ALLOWED" if allowed else "DISALLOWED",
                "elapsed_ms": int((datetime.now() - started).total_seconds() * 1000),
                "error": None,
                "matched_policy": "RobotFileParser.can_fetch returned true" if allowed else "RobotFileParser.can_fetch returned false",
                "crawl_delay": await checker.get_crawl_delay(target),
                "robots_mtime": getattr(parser, "mtime", lambda: None)(),
            }
        except RobotsInconclusiveException as exc:
            _, robots_url = checker._get_robots_url(target)
            results[target] = {
                "robots_url": robots_url,
                "status": "INCONCLUSIVE",
                "elapsed_ms": int((datetime.now() - started).total_seconds() * 1000),
                "error": str(exc),
                "matched_policy": None,
                "crawl_delay": None,
            }
    return results


async def fill_first_matching(page, selectors, value):
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.count() == 0:
                continue
            await locator.click(timeout=2500)
            await locator.fill(value, timeout=2500)
            return selector
        except Exception:
            continue
    return None


async def click_text_candidate(page, candidates):
    for candidate in candidates:
        try:
            loc = page.get_by_text(candidate, exact=False).first
            if await loc.count() == 0:
                continue
            await loc.click(timeout=2500)
            return f"text={candidate}"
        except Exception:
            continue
    return None


async def click_search(page):
    candidates = [
        "button:has-text('Search')",
        "input[type='submit']",
        "[role='button']:has-text('Search')",
        "text=Search",
    ]
    for selector in candidates:
        try:
            await page.locator(selector).first.click(timeout=3000)
            return selector
        except Exception:
            continue
    return None


async def normal_ui_attempt(window: int, collection_date, departure_date) -> dict:
    result = {
        "window": window,
        "collection_date": str(collection_date),
        "departure_date": str(departure_date),
        "advance_window_days": window,
        "status": "PARSER_ERROR",
        "quote_count": 0,
        "final_url": None,
        "http_status": None,
        "page_title": None,
        "form_visible": False,
        "search_submitted": False,
        "results_rendered": False,
        "fields_available": [],
        "sample_observations": [],
        "error": None,
    }
    screenshot_prefix = ARTIFACT_DIR / f"t{window}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="en-IN",
            timezone_id=settings.DAILY_COLLECTION_TIMEZONE,
            user_agent=settings.SCRAPER_USER_AGENT,
        )
        page = await context.new_page()
        responses = []
        console_messages = []
        page.on("response", lambda response: responses.append({"url": response.url, "status": response.status}))
        page.on("console", lambda msg: console_messages.append({"type": msg.type, "text": msg.text[:500]}))
        try:
            response = await page.goto(BOOKING_URL, wait_until="domcontentloaded", timeout=30000)
            result["http_status"] = response.status if response else None
            await page.wait_for_load_state("networkidle", timeout=15000)
            result["final_url"] = page.url
            result["page_title"] = await page.title()
            visible_text = (await page.locator("body").inner_text(timeout=5000))[:12000]
            (ARTIFACT_DIR / f"t{window}_booking_visible_text.txt").write_text(visible_text, encoding="utf-8")
            await page.screenshot(path=str(screenshot_prefix) + "_booking.png", full_page=True)

            lower_text = visible_text.lower()
            if any(term in lower_text for term in CAPTCHA_TERMS):
                result["status"] = "CAPTCHA"
                return result
            if any(term in lower_text for term in BLOCK_TERMS):
                result["status"] = "BLOCKED"
                return result

            result["form_visible"] = any(term in lower_text for term in ("from", "origin", "departure", "search", "one way"))
            await click_text_candidate(page, ["One Way", "Oneway", "OneWay"])

            origin_selector = await fill_first_matching(
                page,
                [
                    "input[placeholder*='From' i]",
                    "input[aria-label*='From' i]",
                    "input[id*='from' i]",
                    "input[name*='from' i]",
                    "input[placeholder*='Origin' i]",
                ],
                "DEL",
            )
            if origin_selector:
                await page.keyboard.press("Enter")

            destination_selector = await fill_first_matching(
                page,
                [
                    "input[placeholder*='To' i]",
                    "input[aria-label*='To' i]",
                    "input[id*='to' i]",
                    "input[name*='to' i]",
                    "input[placeholder*='Destination' i]",
                ],
                "BOM",
            )
            if destination_selector:
                await page.keyboard.press("Enter")

            date_selected = await click_text_candidate(
                page,
                [
                    departure_date.strftime("%d"),
                    departure_date.strftime("%d %b"),
                    departure_date.strftime("%d %B"),
                    departure_date.strftime("%Y-%m-%d"),
                ],
            )
            await click_text_candidate(page, ["Economy", "Adult", "1 Adult"])
            search_selector = await click_search(page)
            result["search_submitted"] = search_selector is not None
            result["interaction"] = {
                "origin_selector": origin_selector,
                "destination_selector": destination_selector,
                "date_selector": date_selected,
                "search_selector": search_selector,
            }
            if not result["search_submitted"] or not origin_selector or not destination_selector:
                result["error"] = "Public booking form selectors were not usable through visible UI."
                return result

            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except PlaywrightTimeoutError:
                result["status"] = "TIMEOUT"
                result["error"] = "Timed out waiting for result navigation/render."
                return result

            result["final_url"] = page.url
            result["page_title"] = await page.title()
            final_text = (await page.locator("body").inner_text(timeout=5000))[:12000]
            (ARTIFACT_DIR / f"t{window}_results_visible_text.txt").write_text(final_text, encoding="utf-8")
            await page.screenshot(path=str(screenshot_prefix) + "_results.png", full_page=True)
            final_lower = final_text.lower()
            if any(term in final_lower for term in CAPTCHA_TERMS):
                result["status"] = "CAPTCHA"
                return result
            if any(term in final_lower for term in BLOCK_TERMS):
                result["status"] = "BLOCKED"
                return result

            flight_card_selectors = [
                "[data-testid*='flight' i]",
                "[class*='flight' i]",
                "[class*='fare' i]",
                "div:has-text('Book Now')",
                "div:has-text('Flight Details')",
            ]
            rendered_count = 0
            for selector in flight_card_selectors:
                try:
                    count = await page.locator(selector).count()
                    rendered_count = max(rendered_count, min(count, 100))
                except Exception:
                    continue
            result["rendered_card_count"] = rendered_count
            result["results_rendered"] = rendered_count > 0
            if not result["results_rendered"]:
                if any(term in final_lower for term in ("no flight", "sold out", "no result", "no fare")):
                    result["status"] = "NO_FLIGHTS"
                else:
                    result["status"] = "NO_FARES"
                return result

            fields = []
            for label, terms in {
                "airline": ("air india", "akasa", "indigo", "spicejet", "vistara"),
                "flight_number": ("qp", "6e", "ai", "sg", "uk"),
                "departure_time": (":",),
                "arrival_time": (":",),
                "total_fare": ("rs", "₹", "inr"),
                "cabin_class": ("economy",),
                "route": ("del", "bom"),
                "departure_date": (departure_date.strftime("%d"), departure_date.strftime("%b")),
            }.items():
                if all(term.lower() in final_lower for term in terms[:1]):
                    fields.append(label)
            result["fields_available"] = fields
            result["quote_count"] = rendered_count
            result["status"] = "SUCCESS" if {"total_fare", "route"}.issubset(set(fields)) else "NO_FARES"
            return result
        except PlaywrightTimeoutError as exc:
            result["status"] = "TIMEOUT"
            result["error"] = str(exc)
            return result
        except Exception as exc:
            result["status"] = "PARSER_ERROR"
            result["error"] = f"{type(exc).__name__}: {exc}"
            return result
        finally:
            (ARTIFACT_DIR / f"t{window}_console.json").write_text(json.dumps(console_messages, indent=2), encoding="utf-8")
            (ARTIFACT_DIR / f"t{window}_network_summary.json").write_text(json.dumps(responses[-100:], indent=2), encoding="utf-8")
            await context.close()
            await browser.close()


def status_allows_continuation(status: str) -> bool:
    return status not in {"CAPTCHA", "BLOCKED", "ROBOTS_DISALLOWED", "ROBOTS_INCONCLUSIVE", "TIMEOUT"}


async def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    tz = ZoneInfo(settings.DAILY_COLLECTION_TIMEZONE)
    collection_date = datetime.now(tz).date()
    before = db_counts()
    robots = await robots_results()
    report = {
        "source": "HappyFares",
        "target": {
            "route": "DEL-BOM",
            "collection_date": str(collection_date),
            "trip": "one-way",
            "passengers": "1 adult",
            "cabin": "Economy",
            "currency": "INR",
            "windows": WINDOWS,
        },
        "robots": robots,
        "robots_result": "ALLOWED",
        "attempts": [],
        "total_usable_observations": 0,
        "production_db_modified": False,
        "db_before": before,
        "db_after": None,
    }

    if any(item["status"] == "DISALLOWED" for item in robots.values()):
        report["robots_result"] = "DISALLOWED"
    elif any(item["status"] == "INCONCLUSIVE" for item in robots.values()):
        report["robots_result"] = "INCONCLUSIVE"

    if report["robots_result"] != "ALLOWED":
        status = "ROBOTS_DISALLOWED" if report["robots_result"] == "DISALLOWED" else "ROBOTS_INCONCLUSIVE"
        for window in WINDOWS:
            report["attempts"].append(
                {
                    "window": window,
                    "status": status,
                    "quote_count": 0,
                    "collection_date": str(collection_date),
                    "departure_date": str(collection_date + timedelta(days=window)),
                    "advance_window_days": window,
                    "error": "Robots permission did not allow the controlled UI test.",
                }
            )
    else:
        for window in WINDOWS:
            departure_date = collection_date + timedelta(days=window)
            attempt = await normal_ui_attempt(window, collection_date, departure_date)
            report["attempts"].append(attempt)
            if attempt["status"] == "SUCCESS":
                report["total_usable_observations"] += attempt.get("quote_count", 0)
            if not status_allows_continuation(attempt["status"]):
                for skipped_window in WINDOWS[WINDOWS.index(window) + 1 :]:
                    report["attempts"].append(
                        {
                            "window": skipped_window,
                            "collection_date": str(collection_date),
                            "departure_date": str(collection_date + timedelta(days=skipped_window)),
                            "advance_window_days": skipped_window,
                            "status": attempt["status"],
                            "quote_count": 0,
                            "error": f"Stopped after T+{window} status {attempt['status']}; no bypass or retry attempted.",
                        }
                    )
                break

    report["db_after"] = db_counts()
    report["production_db_modified"] = report["db_after"] != report["db_before"]
    terminal_statuses = {attempt["status"] for attempt in report["attempts"]}
    report["captcha_or_block"] = bool(terminal_statuses & {"CAPTCHA", "BLOCKED"})
    report["technically_feasible"] = report["total_usable_observations"] > 0 and not report["production_db_modified"]

    (ARTIFACT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    lines = [
        "# HappyFares Controlled Feasibility Diagnostic",
        "",
        f"- Source: HappyFares",
        f"- Route: DEL-BOM",
        f"- Collection date: {collection_date}",
        f"- Database modified: {report['production_db_modified']}",
        f"- Robots result: {report['robots_result']}",
        f"- Total usable observations: {report['total_usable_observations']}",
        "",
        "## Robots",
        "",
        "| Target | Robots URL | Result | Elapsed | Detail |",
        "|---|---|---:|---:|---|",
    ]
    for target, item in robots.items():
        detail = item.get("matched_policy") or item.get("error") or ""
        lines.append(f"| {target} | {item['robots_url']} | {item['status']} | {item['elapsed_ms']} ms | {detail} |")
    lines.extend(["", "## Attempts", "", "| Window | Departure | Status | Quotes | Final URL | Error |", "|---:|---|---|---:|---|---|"])
    for attempt in report["attempts"]:
        lines.append(
            f"| T+{attempt['window']} | {attempt['departure_date']} | {attempt['status']} | "
            f"{attempt.get('quote_count', 0)} | {attempt.get('final_url') or ''} | {attempt.get('error') or ''} |"
        )
    lines.extend(
        [
            "",
            "## Database Counts",
            "",
            f"- Before: {report['db_before']}",
            f"- After: {report['db_after']}",
            "",
            "## Recommendation",
            "",
            "Do not add HappyFares to production source readiness unless a later approved diagnostic proves usable structured fare observations through robots-allowed public UI paths.",
        ]
    )
    (ARTIFACT_DIR / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
