"""Read-only Yatra public UI feasibility and parser diagnostic."""

import asyncio
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


ARTIFACT_DIR = Path(__file__).resolve().parent
DB_PATH = Path(__file__).resolve().parents[2] / "apix.db"
ROBOTS_URL = "https://www.yatra.com/robots.txt"
HOME_URL = "https://www.yatra.com/"
FLIGHTS_URL = "https://www.yatra.com/flights"
SEARCH_HOST = "https://flight.yatra.com/"
USER_AGENT = "APIx-Research-Bot/0.1 (Academic Airfare Index Prototype; Contact: research@example.edu)"
TARGET = {
    "source": "Yatra",
    "route": "DEL-BOM",
    "origin": "DEL",
    "destination": "BOM",
    "collection_date": "2026-09-05",
    "departure_date": "2026-09-06",
    "requested_window": "T+1",
    "advance_window_days": 1,
    "trip": "one-way",
    "passengers": "1 adult",
    "currency": "INR",
}

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
    "error 1020",
    "blocked by cloudflare",
    "unusual traffic",
]
NO_AVAILABILITY_TERMS = [
    "no flights available",
    "no flight available",
    "no results found",
    "we could not find any flights",
]


def db_counts() -> dict:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    counts = {
        "raw_total": cur.execute("select count(*) from raw_airfare_quotes").fetchone()[0],
        "processed_total": cur.execute("select count(*) from processed_airfare_quotes").fetchone()[0],
        "live_raw": cur.execute("select count(*) from raw_airfare_quotes where collection_mode='LIVE'").fetchone()[0],
        "live_processed": cur.execute(
            """
            select count(*)
            from processed_airfare_quotes p
            join raw_airfare_quotes r on r.id = p.raw_quote_id
            where r.collection_mode = 'LIVE'
            """
        ).fetchone()[0],
        "latest_job_id": cur.execute("select max(id) from scraping_job_logs").fetchone()[0],
    }
    con.close()
    return counts


def text_excerpt(text: str, limit: int = 3000) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


async def check_robots() -> dict:
    started = time.perf_counter()
    result = {
        "robots_url": ROBOTS_URL,
        "http_status": None,
        "elapsed_ms": None,
        "targets": [],
        "result": "INCONCLUSIVE",
        "error": None,
    }
    targets = [HOME_URL, FLIGHTS_URL, SEARCH_HOST]
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get(ROBOTS_URL)
        result["http_status"] = response.status_code
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        if response.status_code == 200:
            parser = RobotFileParser()
            parser.set_url(ROBOTS_URL)
            parser.parse(response.text.splitlines())
            all_allowed = True
            for target in targets:
                allowed = bool(parser.can_fetch(USER_AGENT, target))
                all_allowed = all_allowed and allowed
                path = urlparse(target).path or "/"
                matching = []
                current_agent_applies = False
                for raw_line in response.text.splitlines():
                    line = raw_line.strip()
                    lower = line.lower()
                    if lower.startswith("user-agent:"):
                        agent = line.split(":", 1)[1].strip()
                        current_agent_applies = agent == "*" or agent.lower() in USER_AGENT.lower()
                    elif current_agent_applies and (lower.startswith("allow:") or lower.startswith("disallow:")):
                        rule_path = line.split(":", 1)[1].strip()
                        if rule_path and (path.lower().startswith(rule_path.lower()) or rule_path.lower().startswith(path.lower())):
                            matching.append(line)
                result["targets"].append(
                    {
                        "target_url": target,
                        "relevant_path": path,
                        "allowed": allowed,
                        "relevant_rule": matching[:8] or "No specific matching Allow/Disallow rule observed",
                    }
                )
            result["result"] = "ALLOWED" if all_allowed else "DISALLOWED"
        elif response.status_code in (401, 403):
            result["result"] = "DISALLOWED"
            result["error"] = f"robots.txt returned HTTP {response.status_code}; local policy treats as disallow-all"
        else:
            result["error"] = f"robots.txt returned HTTP {response.status_code}"
    except Exception as exc:
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


async def save_state(page, prefix: str) -> str:
    body_text = ""
    try:
        body_text = await page.locator("body").inner_text(timeout=5000)
    except Exception as exc:
        body_text = f"BODY_TEXT_ERROR: {type(exc).__name__}: {exc}"
    try:
        html = await page.content()
        (ARTIFACT_DIR / f"{prefix}.html").write_text(html, encoding="utf-8")
    except Exception:
        pass
    (ARTIFACT_DIR / f"{prefix}_visible_text.txt").write_text(body_text, encoding="utf-8")
    try:
        await page.screenshot(path=str(ARTIFACT_DIR / f"{prefix}.png"), full_page=True)
    except Exception:
        pass
    return body_text


async def click_candidate(page, selectors, log, step, timeout=3000) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector).first()
            await locator.wait_for(state="visible", timeout=timeout)
            await locator.click(timeout=timeout)
            log.append({"step": step, "selector": selector, "status": "ok"})
            return True
        except Exception:
            continue
    log.append({"step": step, "status": "failed", "selectors": selectors})
    return False


async def fill_candidate(page, selectors, value, log, step, timeout=3500) -> bool:
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
            log.append({"step": step, "selector": selector, "value": value, "status": "ok"})
            return True
        except Exception:
            continue
    log.append({"step": step, "value": value, "status": "failed", "selectors": selectors})
    return False


async def press_or_select(page, terms, log, step, timeout=4000) -> bool:
    pattern = re.compile("|".join(re.escape(term) for term in terms), re.I)
    locators = [
        page.get_by_role("option", name=pattern),
        page.locator("li, [role='option'], [role='listbox'] *, .viewport [class], [class*='suggest'] [class]").filter(has_text=pattern),
        page.get_by_text(pattern),
    ]
    for locator in locators:
        try:
            await locator.first.wait_for(state="visible", timeout=timeout)
            await locator.first.click(timeout=timeout)
            log.append({"step": step, "terms": terms, "status": "ok"})
            return True
        except Exception:
            continue
    try:
        await page.keyboard.press("Enter")
        log.append({"step": step, "terms": terms, "status": "enter_pressed"})
        return True
    except Exception:
        pass
    log.append({"step": step, "terms": terms, "status": "failed"})
    return False


def detect_anchors(html: str, text: str) -> dict:
    anchors = {
        "data_testid": sorted(set(re.findall(r'data-testid=["\']([^"\']+)["\']', html)))[:30],
        "aria_labels": sorted(set(re.findall(r'aria-label=["\']([^"\']{1,80})["\']', html)))[:30],
        "roles": sorted(set(re.findall(r'role=["\']([^"\']+)["\']', html)))[:30],
        "semantic_text": [],
    }
    for token in ["From", "To", "Departure", "Travellers", "Search", "Non Stop", "Refundable", "Book"]:
        if re.search(re.escape(token), text, re.I):
            anchors["semantic_text"].append(token)
    return anchors


def sample_observations(text: str) -> list[dict]:
    observations = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for idx, line in enumerate(lines):
        if re.search(r"\b[A-Z0-9]{2}\s?-?\s?\d{2,4}\b", line) or re.search(r"\b(IndiGo|Air India|Akasa|SpiceJet|Vistara)\b", line, re.I):
            window = " | ".join(lines[max(0, idx - 6) : idx + 14])
            fare = re.search(r"(?:INR|Rs\.?|₹)\s*([0-9][0-9,]*)", window, re.I)
            observations.append(
                {
                    "raw_window": window[:1200],
                    "flight_number_candidate": (re.search(r"\b[A-Z0-9]{2}\s?-?\s?\d{2,4}\b", window) or [None])[0],
                    "fare_candidate": fare.group(0) if fare else None,
                }
            )
        if len(observations) >= 5:
            break
    return observations


async def run_browser(report: dict) -> None:
    console = []
    request_failures = []
    statuses = []
    interaction_log = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        report["browser"]["version"] = browser.version
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        page = await context.new_page()
        page.on("console", lambda msg: console.append({"type": msg.type, "text": msg.text[:500]}))
        page.on("requestfailed", lambda req: request_failures.append({"url": req.url, "failure": str(req.failure)}))
        page.on("response", lambda resp: statuses.append({"url": resp.url, "status": resp.status}))

        try:
            response = await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
            report["page"]["home_http_status"] = response.status if response else None
            report["page"]["initial_url"] = HOME_URL
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except PlaywrightTimeoutError:
                interaction_log.append({"step": "home_networkidle", "status": "timeout_continued"})
            await page.wait_for_timeout(2500)
            home_text = await save_state(page, "home")
            report["page"]["home_final_url"] = page.url
            report["page"]["home_title"] = await page.title()

            lower_home = home_text.lower()
            if "flight" not in lower_home:
                response = await page.goto(FLIGHTS_URL, wait_until="domcontentloaded", timeout=30000)
                report["page"]["flights_http_status"] = response.status if response else None
                try:
                    await page.wait_for_load_state("networkidle", timeout=12000)
                except PlaywrightTimeoutError:
                    interaction_log.append({"step": "flights_networkidle", "status": "timeout_continued"})
                await page.wait_for_timeout(2500)
            else:
                report["page"]["flights_http_status"] = report["page"]["home_http_status"]

            initial_text = await save_state(page, "booking")
            initial_html = await page.content()
            lower = f"{initial_text}\n{initial_html}".lower()
            report["page"]["booking_final_url"] = page.url
            report["page"]["booking_title"] = await page.title()
            report["page"]["javascript_rendered"] = bool(initial_text.strip())
            report["page"]["booking_form_visible"] = any(term in lower for term in ["from", "to", "departure", "search"])
            report["blocking"]["captcha"] = any(term in lower for term in CAPTCHA_TERMS)
            report["blocking"]["bot_or_access_block"] = any(term in lower for term in BLOCK_TERMS)
            report["blocking"]["http_403_or_429"] = any(item["status"] in (403, 429) for item in statuses)
            report["stable_anchors"]["booking"] = detect_anchors(initial_html, initial_text)
            report["page"]["visible_text_excerpt"] = text_excerpt(initial_text)

            if report["blocking"]["captcha"] or report["blocking"]["bot_or_access_block"] or report["blocking"]["http_403_or_429"]:
                return

            if not report["page"]["booking_form_visible"]:
                return

            report["interaction"]["one_way_selected"] = await click_candidate(
                page,
                [
                    "text=/^\\s*One\\s*Way\\s*$/i",
                    "label:has-text('One Way')",
                    "[role='radio']:has-text('One Way')",
                    "button:has-text('One Way')",
                ],
                interaction_log,
                "one_way",
            )
            report["interaction"]["origin_selected"] = False
            if await fill_candidate(
                page,
                [
                    "input[aria-label*='Depart' i]",
                    "input[placeholder*='Depart' i]",
                    "input[aria-label*='From' i]",
                    "input[placeholder*='From' i]",
                    "input[name*='origin' i]",
                    "input[id*='origin' i]",
                    "input[name*='from' i]",
                    "input[id*='from' i]",
                ],
                "DEL",
                interaction_log,
                "origin_fill",
            ):
                report["interaction"]["origin_selected"] = await press_or_select(
                    page, ["DEL", "New Delhi", "Delhi"], interaction_log, "origin_suggestion"
                )

            report["interaction"]["destination_selected"] = False
            if await fill_candidate(
                page,
                [
                    "input[aria-label*='Arrival' i]",
                    "input[placeholder*='Arrival' i]",
                    "input[aria-label*='To' i]",
                    "input[placeholder*='To' i]",
                    "input[name*='destination' i]",
                    "input[id*='destination' i]",
                    "input[name*='to' i]",
                    "input[id*='to' i]",
                ],
                "BOM",
                interaction_log,
                "destination_fill",
            ):
                report["interaction"]["destination_selected"] = await press_or_select(
                    page, ["BOM", "Mumbai"], interaction_log, "destination_suggestion"
                )

            date_open = await click_candidate(
                page,
                [
                    "input[aria-label*='Depart' i]",
                    "input[placeholder*='Depart' i]",
                    "input[name*='depart' i]",
                    "input[id*='depart' i]",
                    "text=/Departure/i",
                ],
                interaction_log,
                "date_open",
            )
            report["interaction"]["date_selected"] = False
            if date_open:
                report["interaction"]["date_selected"] = await click_candidate(
                    page,
                    [
                        "[aria-label*='September 6' i]",
                        "[aria-label*='Sep 6' i]",
                        "[aria-label*='06/09/2026' i]",
                        "button:has-text('6')",
                        "text=/^\\s*6\\s*$/",
                    ],
                    interaction_log,
                    "date_select",
                    timeout=4000,
                )

            report["interaction"]["passenger_selected"] = True
            report["interaction"]["currency_inr_available"] = "inr" in lower or "₹" in initial_text
            report["interaction"]["search_submitted"] = await click_candidate(
                page,
                [
                    "button:has-text('Search')",
                    "[role='button']:has-text('Search')",
                    "input[type='submit'][value*='Search' i]",
                    "text=/^\\s*Search\\s*$/i",
                ],
                interaction_log,
                "search",
                timeout=4000,
            )

            if report["interaction"]["search_submitted"]:
                try:
                    await page.wait_for_load_state("networkidle", timeout=18000)
                except PlaywrightTimeoutError:
                    interaction_log.append({"step": "results_networkidle", "status": "timeout_continued"})
                await page.wait_for_timeout(6000)

            final_text = await save_state(page, "results")
            final_html = await page.content()
            final_lower = f"{final_text}\n{final_html}".lower()
            report["results"]["url"] = page.url
            report["results"]["page_title"] = await page.title()
            report["results"]["results_page_reached"] = report["interaction"]["search_submitted"] and (
                page.url != report["page"].get("booking_final_url") or "flight" in final_lower or "fare" in final_lower
            )
            report["results"]["no_availability_visible"] = any(term in final_lower for term in NO_AVAILABILITY_TERMS)
            report["results"]["flight_card_count"] = await page.locator(
                "[data-testid*='flight' i], [class*='flight' i], [class*='airline' i], [class*='fare' i]"
            ).count()
            report["results"]["airline_visible"] = bool(
                re.search(r"\b(IndiGo|Air India|Akasa|SpiceJet|Vistara|AirAsia|Alliance Air)\b", final_text, re.I)
            )
            report["results"]["flight_number_visible"] = bool(re.search(r"\b[A-Z0-9]{2}\s?-?\s?\d{2,4}\b", final_text))
            report["results"]["origin_destination_visible"] = "DEL" in final_text and "BOM" in final_text
            report["results"]["departure_arrival_time_visible"] = bool(re.search(r"\b\d{1,2}:\d{2}\b", final_text))
            report["results"]["duration_visible"] = bool(re.search(r"\b\d{1,2}h(?:\\s*\\d{1,2}m)?\b", final_text, re.I))
            report["results"]["stops_visible"] = any(term in final_lower for term in ["non stop", "non-stop", "1 stop", "stops"])
            report["results"]["fare_visible"] = bool(re.search(r"(?:INR|Rs\.?|₹)\s*[0-9][0-9,]*", final_text, re.I))
            report["results"]["fare_family_visible"] = any(term in final_lower for term in ["saver", "flex", "economy", "refundable"])
            report["results"]["displayed_date_visible"] = any(term in final_lower for term in ["6 sep", "06 sep", "september 6", "06/09/2026"])
            report["results"]["sample_observations"] = sample_observations(final_text)
            report["results"]["visible_text_excerpt"] = text_excerpt(final_text)
            report["stable_anchors"]["results"] = detect_anchors(final_html, final_text)

            report["blocking"]["captcha"] = any(term in final_lower for term in CAPTCHA_TERMS)
            report["blocking"]["bot_or_access_block"] = any(term in final_lower for term in BLOCK_TERMS)
            report["blocking"]["http_403_or_429"] = any(item["status"] in (403, 429) for item in statuses)
        except Exception as exc:
            report["browser_error"] = f"{type(exc).__name__}: {exc}"
        finally:
            report["interaction_log"] = interaction_log
            report["console"] = console[-40:]
            report["network"] = {
                "failed_requests": request_failures[-40:],
                "http_403_429": [item for item in statuses if item["status"] in (403, 429)][-40:],
                "status_sample": statuses[-60:],
            }
            await context.close()
            await browser.close()


def classify(report: dict) -> str:
    if report["robots"]["result"] == "DISALLOWED":
        return "BLOCKED"
    if report["robots"]["result"] != "ALLOWED":
        return "INCONCLUSIVE"
    if report["blocking"]["captcha"] or report["blocking"]["bot_or_access_block"] or report["blocking"]["http_403_or_429"]:
        return "BLOCKED"
    if report.get("browser_error"):
        return "INCONCLUSIVE"
    if report["results"]["no_availability_visible"] and report["interaction"]["search_submitted"]:
        return "READY_WITH_MINOR_GAPS"
    required = [
        "results_page_reached",
        "airline_visible",
        "flight_number_visible",
        "origin_destination_visible",
        "departure_arrival_time_visible",
        "fare_visible",
    ]
    if all(report["results"].get(field) for field in required):
        if report["results"]["fare_family_visible"] and report["results"]["displayed_date_visible"]:
            return "READY"
        return "READY_WITH_MINOR_GAPS"
    if report["interaction"]["search_submitted"] or report["results"]["results_page_reached"]:
        return "INCONCLUSIVE"
    return "NOT_FEASIBLE"


async def main() -> None:
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target": TARGET,
        "database_before": db_counts(),
        "github_reference": {
            "repository": "https://github.com/vishal815/Python-Based-Flight-Data-Scraping-Automating-Data-Collection-for-Analysis",
            "uses_csv_data": False,
            "copied_selectors": False,
        },
        "robots": {},
        "page": {},
        "interaction": {
            "one_way_selected": False,
            "origin_selected": False,
            "destination_selected": False,
            "date_selected": False,
            "passenger_selected": False,
            "currency_inr_available": False,
            "search_submitted": False,
        },
        "results": {
            "url": None,
            "results_page_reached": False,
            "flight_card_count": 0,
            "airline_visible": False,
            "flight_number_visible": False,
            "origin_destination_visible": False,
            "departure_arrival_time_visible": False,
            "duration_visible": False,
            "stops_visible": False,
            "fare_visible": False,
            "fare_family_visible": False,
            "displayed_date_visible": False,
            "no_availability_visible": False,
            "sample_observations": [],
        },
        "blocking": {
            "captcha": False,
            "bot_or_access_block": False,
            "http_403_or_429": False,
        },
        "stable_anchors": {},
        "interaction_log": [],
        "console": [],
        "network": {},
    }
    report["robots"] = await check_robots()
    if report["robots"]["result"] == "ALLOWED":
        await run_browser(report)
    report["database_after"] = db_counts()
    report["database_changed"] = report["database_before"] != report["database_after"]
    report["classification"] = classify(report)
    report["artifacts"] = sorted(p.name for p in ARTIFACT_DIR.iterdir() if p.is_file())
    (ARTIFACT_DIR / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
