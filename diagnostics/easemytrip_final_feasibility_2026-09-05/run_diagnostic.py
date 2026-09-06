"""Final read-only EaseMyTrip public UI feasibility diagnostic.

This diagnostic does not import ingestion services and does not write to apix.db.
It saves only local diagnostic artifacts for the single approved DEL-BOM T+1 flow.
"""

import asyncio
import json
import re
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


ARTIFACT_DIR = Path(__file__).resolve().parent
DB_PATH = Path(__file__).resolve().parents[2] / "apix.db"
USER_AGENT = "APIx-Research-Bot/0.1 (Academic Airfare Index Prototype; Contact: research@example.edu)"

COLLECTION_DATE = date(2026, 9, 5)
DEPARTURE_DATE = COLLECTION_DATE + timedelta(days=1)

BOOKING_URL = "https://www.easemytrip.com/flights/"
ROBOTS_URLS = [
    "https://www.easemytrip.com/robots.txt",
    "https://flight.easemytrip.com/robots.txt",
]

CAPTCHA_TERMS = [
    "captcha",
    "hcaptcha",
    "recaptcha",
    "turnstile",
    "please verify you are a human",
    "perimeterx",
    "px-captcha",
]
BLOCK_TERMS = [
    "access denied",
    "403 forbidden",
    "too many requests",
    "rate limit exceeded",
    "error 1015",
    "error 1020",
    "blocked by cloudflare",
    "unusual traffic",
]
EMPTY_TERMS = [
    "no flights available",
    "no flight available",
    "no results found",
    "we could not find any flights",
    "sorry, no flights",
]


def db_counts() -> dict:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    counts = {
        "raw_total": cur.execute("select count(*) from raw_airfare_quotes").fetchone()[0],
        "processed_total": cur.execute("select count(*) from processed_airfare_quotes").fetchone()[0],
        "live_raw": cur.execute("select count(*) from raw_airfare_quotes where collection_mode='LIVE'").fetchone()[0],
        "mock_raw": cur.execute("select count(*) from raw_airfare_quotes where collection_mode='MOCK'").fetchone()[0],
        "live_processed": cur.execute(
            """
            select count(*)
            from processed_airfare_quotes p
            join raw_airfare_quotes r on r.id = p.raw_quote_id
            where r.collection_mode = 'LIVE'
            """
        ).fetchone()[0],
        "mock_processed": cur.execute(
            """
            select count(*)
            from processed_airfare_quotes p
            join raw_airfare_quotes r on r.id = p.raw_quote_id
            where r.collection_mode = 'MOCK'
            """
        ).fetchone()[0],
        "job_count": cur.execute("select count(*) from scraping_job_logs").fetchone()[0],
        "max_job_id": cur.execute("select max(id) from scraping_job_logs").fetchone()[0],
        "index_count": cur.execute("select count(*) from airfare_index_values").fetchone()[0],
    }
    con.close()
    return counts


def normalize_text(text: str, limit: int = 5000) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


def find_relevant_rules(robots_text: str, path: str) -> list[str]:
    rules = []
    current_agent_applies = False
    lowered_path = path.lower() or "/"
    for raw_line in robots_text.splitlines():
        line = raw_line.strip()
        lower = line.lower()
        if not line or line.startswith("#"):
            continue
        if lower.startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip().lower()
            current_agent_applies = agent == "*" or agent in USER_AGENT.lower()
            continue
        if current_agent_applies and (lower.startswith("allow:") or lower.startswith("disallow:")):
            rule_path = line.split(":", 1)[1].strip()
            comparable = rule_path.replace("*", "").lower()
            if comparable and (
                lowered_path.startswith(comparable)
                or comparable.startswith(lowered_path)
                or lowered_path.startswith(comparable.rstrip("/"))
            ):
                rules.append(line)
    return rules[:12]


async def fetch_robots() -> dict:
    results = {}
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        for robots_url in ROBOTS_URLS:
            started = time.perf_counter()
            item = {
                "url": robots_url,
                "status": None,
                "elapsed_ms": None,
                "error": None,
                "text_file": None,
                "targets": {},
            }
            try:
                response = await client.get(robots_url)
                item["status"] = response.status_code
                item["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
                host = urlparse(robots_url).hostname or "unknown"
                text_path = ARTIFACT_DIR / f"{host.replace('.', '_')}_robots.txt"
                text_path.write_text(response.text, encoding="utf-8")
                item["text_file"] = text_path.name

                if response.status_code == 200:
                    parser = RobotFileParser()
                    parser.set_url(robots_url)
                    parser.parse(response.text.splitlines())
                    for target in [
                        BOOKING_URL,
                        "https://www.easemytrip.com/flight-search/listing",
                        "https://flight.easemytrip.com/flightlist",
                    ]:
                        target_host = urlparse(target).hostname
                        if target_host != host:
                            continue
                        path = urlparse(target).path or "/"
                        allowed = bool(parser.can_fetch(USER_AGENT, target))
                        item["targets"][target] = {
                            "hostname": target_host,
                            "path": path,
                            "allowed": allowed,
                            "relevant_rules": find_relevant_rules(response.text, path),
                        }
                elif response.status_code in (401, 403):
                    item["error"] = f"robots.txt returned HTTP {response.status_code}"
                else:
                    item["error"] = f"robots.txt returned HTTP {response.status_code}"
            except Exception as exc:
                item["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
                item["error"] = f"{type(exc).__name__}: {exc}"
            results[robots_url] = item
    return results


async def save_page_state(page, name: str) -> dict:
    body_text = ""
    try:
        body_text = await page.locator("body").inner_text(timeout=5000)
    except Exception as exc:
        body_text = f"BODY_TEXT_ERROR: {type(exc).__name__}: {exc}"

    try:
        html = await page.content()
        (ARTIFACT_DIR / f"{name}.html").write_text(html, encoding="utf-8")
    except Exception as exc:
        html = f"HTML_ERROR: {type(exc).__name__}: {exc}"

    (ARTIFACT_DIR / f"{name}_visible_text.txt").write_text(body_text, encoding="utf-8")
    try:
        await page.screenshot(path=str(ARTIFACT_DIR / f"{name}.png"), full_page=True)
    except Exception:
        pass
    return {
        "url": page.url,
        "hostname": urlparse(page.url).hostname,
        "pathname": urlparse(page.url).path or "/",
        "title": await page.title(),
        "visible_text_excerpt": normalize_text(body_text),
        "html_excerpt": normalize_text(html, 1000),
    }


async def visible_click(page, selectors: list[str], log: list[dict], step: str, timeout: int = 3500) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector).first()
            await locator.wait_for(state="visible", timeout=timeout)
            await locator.click(timeout=timeout)
            log.append({"step": step, "status": "PASS", "selector": selector})
            return True
        except Exception:
            continue
    log.append({"step": step, "status": "FAIL", "selectors": selectors})
    return False


async def visible_fill(page, selectors: list[str], value: str, log: list[dict], step: str, timeout: int = 3500) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector).first()
            await locator.wait_for(state="visible", timeout=timeout)
            await locator.click(timeout=timeout)
            try:
                await locator.fill("", timeout=timeout)
            except Exception:
                pass
            await locator.fill(value, timeout=timeout)
            log.append({"step": step, "status": "PASS", "selector": selector, "value": value})
            return True
        except Exception:
            continue
    log.append({"step": step, "status": "FAIL", "selectors": selectors, "value": value})
    return False


async def select_visible_text(page, terms: list[str], log: list[dict], step: str, timeout: int = 4000) -> bool:
    pattern = re.compile("|".join(re.escape(term) for term in terms), re.I)
    locators = [
        page.get_by_role("option", name=pattern),
        page.locator("li, [role='option'], [role='listbox'] *, [class*='airport' i], [class*='suggest' i]").filter(
            has_text=pattern
        ),
        page.get_by_text(pattern),
    ]
    for locator in locators:
        try:
            await locator.first.wait_for(state="visible", timeout=timeout)
            await locator.first.click(timeout=timeout)
            log.append({"step": step, "status": "PASS", "terms": terms})
            return True
        except Exception:
            continue
    try:
        await page.keyboard.press("Enter")
        log.append({"step": step, "status": "ENTER_PRESSED", "terms": terms})
        return True
    except Exception:
        pass
    log.append({"step": step, "status": "FAIL", "terms": terms})
    return False


async def collect_stable_anchors(page) -> dict:
    html = await page.content()
    text = await page.locator("body").inner_text(timeout=5000)
    return {
        "data_testid": sorted(set(re.findall(r'data-testid=["\']([^"\']+)["\']', html)))[:40],
        "aria_labels": sorted(set(re.findall(r'aria-label=["\']([^"\']{1,100})["\']', html)))[:40],
        "roles": sorted(set(re.findall(r'role=["\']([^"\']+)["\']', html)))[:40],
        "semantic_text": [
            token
            for token in [
                "One-Way",
                "One Way",
                "FROM",
                "TO",
                "DEPARTURE DATE",
                "TRAVELLER & CLASS",
                "SEARCH",
                "[DEL]",
                "[BOM]",
                "Economy",
            ]
            if token.lower() in text.lower()
        ],
    }


def page_status_for_url(statuses: list[dict], final_url: str) -> int | None:
    for item in reversed(statuses):
        if item["url"] == final_url:
            return item["status"]
    return None


async def run_browser(report: dict) -> None:
    console = []
    failed_requests = []
    responses = []
    navigation = []
    log = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        report["browser"]["browser_version"] = browser.version
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 900},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        page = await context.new_page()
        page.on("console", lambda msg: console.append({"type": msg.type, "text": msg.text[:500]}))
        page.on("requestfailed", lambda req: failed_requests.append({"url": req.url, "failure": str(req.failure)}))
        page.on("response", lambda resp: responses.append({"url": resp.url, "status": resp.status}))
        page.on("framenavigated", lambda frame: navigation.append({"url": frame.url}) if frame == page.main_frame else None)

        try:
            response = await page.goto(BOOKING_URL, wait_until="domcontentloaded", timeout=30000)
            report["browser"]["booking_http_status"] = response.status if response else None
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except PlaywrightTimeoutError:
                log.append({"step": "booking_networkidle", "status": "TIMEOUT_CONTINUED"})
            await page.wait_for_timeout(2500)
            report["booking_page"] = await save_page_state(page, "booking_page")
            report["booking_page"]["anchors"] = await collect_stable_anchors(page)

            visible = report["booking_page"]["visible_text_excerpt"]
            combined_lower = (visible + "\n" + report["booking_page"]["html_excerpt"]).lower()
            report["browser"]["public_ui_reachable"] = True
            report["browser"]["javascript_renders"] = bool(visible.strip())
            report["browser"]["booking_form_visible"] = all(term in combined_lower for term in ["from", "to"]) and (
                "search" in combined_lower
            )
            report["blocking"]["captcha"] = any(term in combined_lower for term in CAPTCHA_TERMS)
            report["blocking"]["access_blocked"] = any(term in combined_lower for term in BLOCK_TERMS)
            report["blocking"]["http_403_429"] = any(item["status"] in (403, 429) for item in responses)

            if report["blocking"]["captcha"] or report["blocking"]["access_blocked"] or report["blocking"]["http_403_429"]:
                return

            if not report["browser"]["booking_form_visible"]:
                report["result"]["event_classification"] = "UI_INTERACTION_FAILURE"
                return

            await visible_click(
                page,
                [
                    "text=/^\\s*One\\s*-?\\s*Way\\s*$/i",
                    "button:has-text('One-Way')",
                    "button:has-text('One Way')",
                    "[role='radio']:has-text('One')",
                ],
                log,
                "select_one_way",
            )

            origin_selected = False
            if await visible_fill(
                page,
                [
                    "input[placeholder*='From' i]",
                    "input[aria-label*='From' i]",
                    "input[name*='from' i]",
                    "input[id*='from' i]",
                    "input[name*='origin' i]",
                    "input[id*='origin' i]",
                ],
                "DEL",
                log,
                "fill_origin",
            ):
                origin_selected = await select_visible_text(page, ["DEL", "Delhi", "New Delhi"], log, "select_origin")
            elif await visible_click(page, ["text=/FROM/i", "text=/\\[DEL\\]/"], log, "open_origin"):
                await page.keyboard.press("Control+A")
                await page.keyboard.type("DEL")
                origin_selected = await select_visible_text(page, ["DEL", "Delhi", "New Delhi"], log, "select_origin")

            destination_selected = False
            if await visible_fill(
                page,
                [
                    "input[placeholder*='To' i]",
                    "input[aria-label*='To' i]",
                    "input[name*='to' i]",
                    "input[id*='to' i]",
                    "input[name*='destination' i]",
                    "input[id*='destination' i]",
                ],
                "BOM",
                log,
                "fill_destination",
            ):
                destination_selected = await select_visible_text(page, ["BOM", "Mumbai"], log, "select_destination")
            elif await visible_click(page, ["text=/TO/i", "text=/\\[BOM\\]/"], log, "open_destination"):
                await page.keyboard.press("Control+A")
                await page.keyboard.type("BOM")
                destination_selected = await select_visible_text(page, ["BOM", "Mumbai"], log, "select_destination")

            date_opened = await visible_click(
                page,
                [
                    "input[placeholder*='Depart' i]",
                    "input[aria-label*='Depart' i]",
                    "input[name*='depart' i]",
                    "input[id*='depart' i]",
                    "text=/DEPARTURE DATE/i",
                    "text=/Departure/i",
                ],
                log,
                "open_date_picker",
            )
            date_selected = False
            if date_opened:
                date_selected = await visible_click(
                    page,
                    [
                        "[aria-label*='September 6' i]",
                        "[aria-label*='Sep 6' i]",
                        "[aria-label*='6 September' i]",
                        "[aria-label*='06/09/2026' i]",
                        "button:has-text('6')",
                        "td:has-text('6')",
                        "div:has-text('6'):has-text('₹')",
                        "text=/^\\s*6\\s*$/",
                    ],
                    log,
                    "select_departure_date",
                    timeout=5000,
                )

            report["interaction"]["one_way"] = True
            report["interaction"]["origin_del"] = origin_selected
            report["interaction"]["destination_bom"] = destination_selected
            report["interaction"]["departure_date"] = date_selected
            report["interaction"]["adult_economy"] = "1" in visible and "economy" in combined_lower

            await save_page_state(page, "after_inputs")

            submitted = await visible_click(
                page,
                [
                    "button:has-text('SEARCH')",
                    "button:has-text('Search')",
                    "[role='button']:has-text('SEARCH')",
                    "[role='button']:has-text('Search')",
                    "input[type='submit'][value*='Search' i]",
                    "text=/^\\s*SEARCH\\s*$/i",
                    "text=/^\\s*Search\\s*$/i",
                ],
                log,
                "submit_search",
                timeout=5000,
            )
            report["interaction"]["search_submitted"] = submitted
            if submitted:
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                except PlaywrightTimeoutError:
                    log.append({"step": "post_search_domcontentloaded", "status": "TIMEOUT_CONTINUED"})
                try:
                    await page.wait_for_load_state("networkidle", timeout=18000)
                except PlaywrightTimeoutError:
                    log.append({"step": "post_search_networkidle", "status": "TIMEOUT_CONTINUED"})
                await page.wait_for_timeout(8000)

            report["results_page"] = await save_page_state(page, "results_page")
            final_text = report["results_page"]["visible_text_excerpt"]
            final_lower = final_text.lower()
            final_url = page.url
            report["result"]["final_url"] = final_url
            report["result"]["hostname"] = urlparse(final_url).hostname
            report["result"]["pathname"] = urlparse(final_url).path or "/"
            report["result"]["http_status"] = page_status_for_url(responses, final_url)
            report["result"]["page_title"] = await page.title()
            report["result"]["empty_results"] = any(term in final_lower for term in EMPTY_TERMS)
            report["result"]["route_unavailable"] = "route unavailable" in final_lower
            report["result"]["cards_visible"] = await page.locator(
                "[data-testid*='flight' i], [class*='flight' i], [class*='airline' i], [class*='fare' i]"
            ).count()
            report["result"]["genuine_results_rendered"] = submitted and (
                final_url != BOOKING_URL
                and any(term in final_lower for term in ["flight", "airline", "non stop", "book", "fare"])
            )
            report["blocking"]["captcha"] = any(term in final_lower for term in CAPTCHA_TERMS)
            report["blocking"]["access_blocked"] = any(term in final_lower for term in BLOCK_TERMS)
            report["blocking"]["http_403_429"] = any(item["status"] in (403, 429) for item in responses)

            fare_pattern = re.compile(r"(?:INR|Rs\.?|₹)\s*([0-9][0-9,]*)", re.I)
            report["fare_extraction"] = {
                "attempted": bool(report["result"]["genuine_results_rendered"]),
                "airline_visible": bool(
                    re.search(r"\b(IndiGo|Air India|Akasa|SpiceJet|Vistara|AirAsia|Alliance Air)\b", final_text, re.I)
                ),
                "flight_number_visible": bool(re.search(r"\b[A-Z0-9]{2}\s?-?\s?\d{2,4}\b", final_text)),
                "departure_time_visible": bool(re.search(r"\b\d{1,2}:\d{2}\b", final_text)),
                "arrival_time_visible": bool(re.search(r"\b\d{1,2}:\d{2}\b", final_text)),
                "total_fare_visible": bool(fare_pattern.search(final_text)),
                "cabin_or_fare_family_visible": any(
                    term in final_lower for term in ["economy", "saver", "flex", "refundable", "cabin"]
                ),
                "departure_date_visible": any(term in final_lower for term in ["6sep", "6 sep", "06 sep", "september 6"]),
                "route_visible": "del" in final_lower and "bom" in final_lower,
                "sample_visible_windows": [],
            }

            if report["fare_extraction"]["attempted"]:
                lines = [line.strip() for line in final_text.splitlines() if line.strip()]
                for index, line in enumerate(lines):
                    if fare_pattern.search(line) or re.search(r"\b[A-Z0-9]{2}\s?-?\s?\d{2,4}\b", line):
                        report["fare_extraction"]["sample_visible_windows"].append(
                            " | ".join(lines[max(index - 6, 0) : index + 12])[:1200]
                        )
                    if len(report["fare_extraction"]["sample_visible_windows"]) >= 3:
                        break

            report["results_page"]["anchors"] = await collect_stable_anchors(page)
        except Exception as exc:
            report["browser"]["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            report["interaction_log"] = log
            report["console_summary"] = console[-40:]
            report["navigation_summary"] = navigation[-40:]
            report["network_summary"] = {
                "failed_requests": failed_requests[-40:],
                "http_403_429": [item for item in responses if item["status"] in (403, 429)][-40:],
                "document_or_navigation_responses": [
                    item
                    for item in responses
                    if any(marker in item["url"] for marker in ["easemytrip.com/flights", "flight.easemytrip.com", "flight-search"])
                ][-40:],
            }
            await context.close()
            await browser.close()


def robots_permission_for_result_path(report: dict) -> str:
    host = report["result"].get("hostname")
    final_url = report["result"].get("final_url")
    path = report["result"].get("pathname")
    if not host or not final_url or not path:
        return "INCONCLUSIVE"
    if final_url == BOOKING_URL or not report["result"].get("genuine_results_rendered"):
        return "INCONCLUSIVE"

    robots_url = f"https://{host}/robots.txt"
    item = report["robots"].get(robots_url)
    if not item or item.get("status") != 200:
        return "INCONCLUSIVE"
    target = item.get("targets", {}).get(final_url)
    if target:
        return "ALLOWED" if target["allowed"] else "DISALLOWED"

    parser = RobotFileParser()
    robots_file = ARTIFACT_DIR / f"{host.replace('.', '_')}_robots.txt"
    if not robots_file.exists():
        return "INCONCLUSIVE"
    parser.parse(robots_file.read_text(encoding="utf-8").splitlines())
    return "ALLOWED" if parser.can_fetch(USER_AGENT, final_url) else "DISALLOWED"


def classify_event(report: dict) -> str:
    if report["blocking"].get("captcha"):
        return "CAPTCHA"
    if report["blocking"].get("access_blocked") or report["blocking"].get("http_403_429"):
        return "ACCESS_BLOCKED"
    if report["browser"].get("error"):
        return "TIMEOUT" if "Timeout" in report["browser"]["error"] else "UI_INTERACTION_FAILURE"
    permission = robots_permission_for_result_path(report)
    if permission == "DISALLOWED":
        return "ROBOTS_DISALLOWED"
    if report["result"].get("empty_results"):
        return "EMPTY_RESULTS"
    if report["result"].get("route_unavailable"):
        return "ROUTE_UNAVAILABLE"
    if not report["interaction"].get("search_submitted") or not report["result"].get("genuine_results_rendered"):
        return "UI_INTERACTION_FAILURE"
    if permission == "INCONCLUSIVE":
        return "ROBOTS_INCONCLUSIVE"
    return "SUCCESS"


def classify_overall(report: dict) -> str:
    event = report["result"]["event_classification"]
    result_permission = report["result"]["robots_permission"]
    extraction = report["fare_extraction"]
    extraction_ready = all(
        extraction.get(key)
        for key in [
            "airline_visible",
            "flight_number_visible",
            "departure_time_visible",
            "arrival_time_visible",
            "total_fare_visible",
            "departure_date_visible",
            "route_visible",
        ]
    )
    if event == "SUCCESS" and result_permission == "ALLOWED" and extraction_ready:
        return "READY"
    if event in {"ROBOTS_DISALLOWED", "ACCESS_BLOCKED", "CAPTCHA"}:
        return "NOT_FEASIBLE"
    if event == "UI_INTERACTION_FAILURE" and report.get("previous_status") == "INCONCLUSIVE":
        return "NOT_FEASIBLE"
    return "INCONCLUSIVE"


def write_markdown(report: dict) -> None:
    extraction = report["fare_extraction"]
    fields = [
        name
        for name, available in [
            ("airline", extraction.get("airline_visible")),
            ("flight number", extraction.get("flight_number_visible")),
            ("departure time", extraction.get("departure_time_visible")),
            ("arrival time", extraction.get("arrival_time_visible")),
            ("total fare", extraction.get("total_fare_visible")),
            ("cabin/fare family", extraction.get("cabin_or_fare_family_visible")),
            ("route", extraction.get("route_visible")),
            ("departure date", extraction.get("departure_date_visible")),
        ]
        if available
    ]
    unresolved = "none"
    if report["overall_classification"] == "INCONCLUSIVE":
        unresolved = (
            "The normal UI flow did not provide enough evidence to confirm both a usable results page "
            "and robots permission for the actual results path."
        )
    if report["overall_classification"] == "NOT_FEASIBLE":
        unresolved = report["not_feasible_reason"]

    lines = [
        "# EASEMYTRIP FINAL FEASIBILITY",
        "",
        "## Scope",
        "",
        f"- Route: {report['target']['route']}",
        f"- Collection date: {report['target']['collection_date']}",
        f"- Departure date: {report['target']['departure_date']}",
        f"- Advance window: {report['target']['advance_window_days']}",
        "- Trip: one-way",
        "- Passengers: 1 adult",
        "- Cabin: Economy",
        "- Database writes: none",
        "- Scraping jobs created: none",
        "- Production scraper created: none",
        "",
        "## Summary",
        "",
        f"- robots permission: {report['robots_permission']}",
        f"- results path: {report['result'].get('final_url') or 'not reached'}",
        f"- results path robots permission: {report['result'].get('robots_permission')}",
        f"- public UI reachable: {'YES' if report['browser'].get('public_ui_reachable') else 'NO'}",
        f"- search interaction: {report['search_interaction']}",
        f"- results rendered: {'YES' if report['result'].get('genuine_results_rendered') else 'NO'}",
        f"- fare extraction: {'PASS' if report['fare_extraction_pass'] else 'FAIL'}",
        f"- CAPTCHA/block: {'YES' if report['captcha_or_block'] else 'NO'}",
        f"- event classification: {report['result']['event_classification']}",
        f"- overall classification: {report['overall_classification']}",
        "",
        "## Robots",
        "",
        "| URL | Status | Timing | Relevant result |",
        "|---|---:|---:|---|",
    ]
    for robots_url, item in report["robots"].items():
        targets = []
        for target, target_item in item.get("targets", {}).items():
            targets.append(
                f"{urlparse(target).hostname}{urlparse(target).path}: "
                f"{'ALLOWED' if target_item['allowed'] else 'DISALLOWED'}"
            )
        lines.append(
            f"| {robots_url} | {item.get('status')} | {item.get('elapsed_ms')} ms | "
            f"{'; '.join(targets) or item.get('error') or 'no target result'} |"
        )
    lines.extend(
        [
            "",
            "## Browser And Interaction",
            "",
            f"- Browser version: {report['browser'].get('browser_version')}",
            f"- Booking HTTP status: {report['browser'].get('booking_http_status')}",
            f"- Booking URL: {report['booking_page'].get('url')}",
            f"- Booking title: {report['booking_page'].get('title')}",
            f"- JavaScript rendering: {'YES' if report['browser'].get('javascript_renders') else 'NO'}",
            f"- Booking form visible: {'YES' if report['browser'].get('booking_form_visible') else 'NO'}",
            f"- Origin DEL selected: {'YES' if report['interaction'].get('origin_del') else 'NO'}",
            f"- Destination BOM selected: {'YES' if report['interaction'].get('destination_bom') else 'NO'}",
            f"- Departure date selected: {'YES' if report['interaction'].get('departure_date') else 'NO'}",
            f"- Search submitted: {'YES' if report['interaction'].get('search_submitted') else 'NO'}",
            "",
            "## Results And Fare Visibility",
            "",
            f"- Final URL: {report['result'].get('final_url')}",
            f"- Hostname: {report['result'].get('hostname')}",
            f"- Pathname: {report['result'].get('pathname')}",
            f"- HTTP status for final URL: {report['result'].get('http_status')}",
            f"- Page title: {report['result'].get('page_title')}",
            f"- Flight card candidates visible: {report['result'].get('cards_visible')}",
            f"- Required fields available: {', '.join(fields) if fields else 'none'}",
            f"- Empty results visible: {'YES' if report['result'].get('empty_results') else 'NO'}",
            "",
            "Calendar fare hints, if present, were not treated as flight quotes.",
            "",
            "## Stable UI Anchors Observed",
            "",
        ]
    )
    anchors = report["booking_page"].get("anchors", {})
    for key, values in anchors.items():
        if values:
            lines.append(f"- booking {key}: {', '.join(values[:20])}")
    result_anchors = report["results_page"].get("anchors", {})
    for key, values in result_anchors.items():
        if values:
            lines.append(f"- results {key}: {', '.join(values[:20])}")
    if not any(anchors.values()) and not any(result_anchors.values()):
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Classification Detail",
            "",
            f"- Unresolved issue / reason: {unresolved}",
            "",
            "## Database",
            "",
            f"- Before: {report['database_before']}",
            f"- After: {report['database_after']}",
            f"- Database changed: {'YES' if report['database_changed'] else 'NO'}",
            "",
            "## Artifacts",
            "",
        ]
    )
    for artifact in report["artifacts"]:
        lines.append(f"- {artifact}")
    (ARTIFACT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main() -> None:
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "previous_status": "INCONCLUSIVE",
        "target": {
            "source": "EaseMyTrip",
            "route": "DEL-BOM",
            "origin": "DEL",
            "destination": "BOM",
            "collection_date": COLLECTION_DATE.isoformat(),
            "departure_date": DEPARTURE_DATE.isoformat(),
            "advance_window_days": 1,
            "trip": "one-way",
            "passengers": "1 adult",
            "cabin": "Economy",
        },
        "database_before": db_counts(),
        "robots": await fetch_robots(),
        "robots_permission": "INCONCLUSIVE",
        "browser": {
            "public_ui_reachable": False,
            "javascript_renders": False,
            "booking_form_visible": False,
        },
        "booking_page": {},
        "interaction": {
            "one_way": False,
            "origin_del": False,
            "destination_bom": False,
            "departure_date": False,
            "adult_economy": False,
            "search_submitted": False,
        },
        "results_page": {},
        "result": {
            "final_url": None,
            "hostname": None,
            "pathname": None,
            "http_status": None,
            "page_title": None,
            "genuine_results_rendered": False,
            "cards_visible": 0,
            "empty_results": False,
            "route_unavailable": False,
            "robots_permission": "INCONCLUSIVE",
            "event_classification": "ROBOTS_INCONCLUSIVE",
        },
        "fare_extraction": {
            "attempted": False,
            "airline_visible": False,
            "flight_number_visible": False,
            "departure_time_visible": False,
            "arrival_time_visible": False,
            "total_fare_visible": False,
            "cabin_or_fare_family_visible": False,
            "departure_date_visible": False,
            "route_visible": False,
            "sample_visible_windows": [],
        },
        "blocking": {
            "captcha": False,
            "access_blocked": False,
            "http_403_429": False,
        },
        "interaction_log": [],
        "console_summary": [],
        "navigation_summary": [],
        "network_summary": {},
    }

    booking_target = report["robots"].get("https://www.easemytrip.com/robots.txt", {}).get("targets", {}).get(BOOKING_URL)
    if booking_target and booking_target["allowed"]:
        await run_browser(report)

    report["result"]["robots_permission"] = robots_permission_for_result_path(report)
    if report["result"]["robots_permission"] == "DISALLOWED":
        report["robots_permission"] = "DISALLOWED"
    elif report["result"]["robots_permission"] == "ALLOWED":
        report["robots_permission"] = "ALLOWED"
    else:
        report["robots_permission"] = "INCONCLUSIVE"

    report["search_interaction"] = "PASS" if report["interaction"].get("search_submitted") else "FAIL"
    report["captcha_or_block"] = any(report["blocking"].values())
    report["fare_extraction_pass"] = bool(
        report["result"].get("genuine_results_rendered")
        and report["fare_extraction"].get("flight_number_visible")
        and report["fare_extraction"].get("total_fare_visible")
    )
    report["result"]["event_classification"] = classify_event(report)
    report["not_feasible_reason"] = "Normal visible UI search did not reach a usable results page in two diagnostics."
    if report["result"]["event_classification"] == "ROBOTS_DISALLOWED":
        report["not_feasible_reason"] = "The actual result path is explicitly disallowed by robots.txt."
    elif report["result"]["event_classification"] in {"ACCESS_BLOCKED", "CAPTCHA"}:
        report["not_feasible_reason"] = "Access block or CAPTCHA was observed."
    report["overall_classification"] = classify_overall(report)
    report["database_after"] = db_counts()
    report["database_changed"] = report["database_before"] != report["database_after"]
    report["artifacts"] = sorted(p.name for p in ARTIFACT_DIR.iterdir() if p.is_file() and p.name != "report.json")
    (ARTIFACT_DIR / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["artifacts"] = sorted(p.name for p in ARTIFACT_DIR.iterdir() if p.is_file())
    write_markdown(report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
