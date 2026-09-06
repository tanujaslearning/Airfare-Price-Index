"""Read-only Air India public booking UI feasibility diagnostic.

This script does not import ingestion services and only reads apix.db counts.
"""

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
ROBOTS_URL = "https://www.airindia.com/robots.txt"
BOOKING_URL = "https://www.airindia.com/en-in/book-flights/"
USER_AGENT = "APIx-Research-Bot/0.1 (Academic Airfare Index Prototype; Contact: research@example.edu)"
TARGET = {
    "source": "Air India",
    "route": "DEL-BOM",
    "origin": "DEL",
    "destination": "BOM",
    "requested_window": "T+7",
    "advance_window_days": 7,
    "departure_date": "2026-09-12",
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
]
NO_AVAILABILITY_TERMS = [
    "no flights available",
    "no flight available",
    "sold out",
    "no results found",
    "we could not find any flights",
]


def db_counts() -> dict:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    counts = {
        "raw_total": cur.execute("select count(*) from raw_airfare_quotes").fetchone()[0],
        "processed_total": cur.execute("select count(*) from processed_airfare_quotes").fetchone()[0],
        "live_raw": cur.execute(
            "select count(*) from raw_airfare_quotes where collection_mode='LIVE'"
        ).fetchone()[0],
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


def visibleish_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</(p|div|li|td|th|tr|h[1-6]|button|label)>", "\n", html)
    html = re.sub(r"<[^>]+>", " ", html)
    return "\n".join(line.strip() for line in re.sub(r"\s+", " ", html).splitlines() if line.strip())


def summarize_visible_text(text: str, limit: int = 5000) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:limit]


async def check_robots() -> dict:
    started = time.perf_counter()
    result = {
        "robots_url": ROBOTS_URL,
        "target_url": BOOKING_URL,
        "relevant_path": urlparse(BOOKING_URL).path,
        "http_status": None,
        "elapsed_ms": None,
        "allowed": None,
        "result": "INCONCLUSIVE",
        "relevant_rule": None,
        "error": None,
    }
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get(ROBOTS_URL)
        result["http_status"] = response.status_code
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        if response.status_code == 200:
            parser = RobotFileParser()
            parser.set_url(ROBOTS_URL)
            parser.parse(response.text.splitlines())
            allowed = parser.can_fetch(USER_AGENT, BOOKING_URL)
            result["allowed"] = bool(allowed)
            result["result"] = "ALLOWED" if allowed else "DISALLOWED"
            path = result["relevant_path"].lower()
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
                    if rule_path and (path.startswith(rule_path.lower()) or rule_path.lower().startswith(path)):
                        matching.append(line)
            result["relevant_rule"] = matching[:5] or "No specific matching Allow/Disallow rule observed"
        elif response.status_code in (401, 403):
            result["allowed"] = False
            result["result"] = "DISALLOWED"
            result["relevant_rule"] = f"robots.txt returned HTTP {response.status_code}; local policy treats as disallow-all"
        else:
            result["result"] = "INCONCLUSIVE"
            result["error"] = f"robots.txt returned HTTP {response.status_code}"
    except Exception as exc:
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


async def click_first(page, selectors, log, step, timeout=2500) -> bool:
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


async def fill_first(page, selectors, value, log, step, timeout=2500) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector).first()
            await locator.wait_for(state="visible", timeout=timeout)
            await locator.click(timeout=timeout)
            await locator.fill(value, timeout=timeout)
            log.append({"step": step, "selector": selector, "value": value, "status": "ok"})
            return True
        except Exception:
            continue
    log.append({"step": step, "value": value, "status": "failed", "selectors": selectors})
    return False


async def select_suggestion(page, terms, log, step, timeout=3500) -> bool:
    pattern = re.compile("|".join(re.escape(term) for term in terms), re.I)
    locators = [
        page.get_by_role("option", name=pattern),
        page.get_by_text(pattern),
        page.locator("li, [role='option'], [role='listbox'] *").filter(has_text=pattern),
    ]
    for locator in locators:
        try:
            await locator.first.wait_for(state="visible", timeout=timeout)
            await locator.first.click(timeout=timeout)
            log.append({"step": step, "terms": terms, "status": "ok"})
            return True
        except Exception:
            continue
    log.append({"step": step, "terms": terms, "status": "failed"})
    return False


async def run_browser_diagnostic(report: dict) -> None:
    console_messages = []
    network_failures = []
    response_statuses = []
    interaction_log = []
    rendered_text = ""

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        report["browser"]["version"] = browser.version
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        page = await context.new_page()
        page.on("console", lambda msg: console_messages.append({"type": msg.type, "text": msg.text[:500]}))
        page.on("requestfailed", lambda req: network_failures.append({"url": req.url, "failure": str(req.failure)}))
        page.on("response", lambda resp: response_statuses.append({"url": resp.url, "status": resp.status}))

        try:
            response = await page.goto(BOOKING_URL, wait_until="domcontentloaded", timeout=30000)
            report["browser"]["http_status"] = response.status if response else None
            report["browser"]["initial_url"] = BOOKING_URL
            report["browser"]["final_url"] = page.url
            report["browser"]["page_title"] = await page.title()
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except PlaywrightTimeoutError:
                interaction_log.append({"step": "networkidle", "status": "timeout_continued"})
            await page.wait_for_timeout(2500)

            html = await page.content()
            rendered_text = summarize_visible_text(await page.locator("body").inner_text(timeout=5000))
            (ARTIFACT_DIR / "initial.html").write_text(html, encoding="utf-8")
            (ARTIFACT_DIR / "initial_visible_text.txt").write_text(rendered_text, encoding="utf-8")
            await page.screenshot(path=str(ARTIFACT_DIR / "initial.png"), full_page=True)

            lower_text = f"{rendered_text}\n{html}".lower()
            report["application_rendering"]["javascript_rendered"] = bool(rendered_text)
            report["application_rendering"]["visible_text_excerpt"] = rendered_text[:2000]
            report["application_rendering"]["booking_form_visible"] = any(
                term in lower_text for term in ["book a flight", "book flights", "from", "to", "departure"]
            )
            report["blocking"]["captcha"] = any(term in lower_text for term in CAPTCHA_TERMS)
            report["blocking"]["bot_or_access_block"] = any(term in lower_text for term in BLOCK_TERMS)
            report["blocking"]["http_403_or_429"] = any(item["status"] in (403, 429) for item in response_statuses)

            if report["blocking"]["captcha"] or report["blocking"]["bot_or_access_block"] or report["blocking"]["http_403_or_429"]:
                return

            if not report["application_rendering"]["booking_form_visible"]:
                return

            report["booking_interaction"]["one_way_selected"] = await click_first(
                page,
                [
                    "text=/^\\s*one\\s*-?\\s*way\\s*$/i",
                    "button:has-text('One Way')",
                    "[role='radio']:has-text('One Way')",
                ],
                interaction_log,
                "select_one_way",
            )

            origin_filled = await fill_first(
                page,
                [
                    "input[placeholder*='From' i]",
                    "input[aria-label*='From' i]",
                    "input[name*='origin' i]",
                    "input[id*='origin' i]",
                    "input[name*='from' i]",
                    "input[id*='from' i]",
                ],
                "DEL",
                interaction_log,
                "fill_origin",
            )
            origin_selected = origin_filled and await select_suggestion(
                page, ["DEL", "Delhi", "New Delhi"], interaction_log, "select_origin_suggestion"
            )

            destination_filled = await fill_first(
                page,
                [
                    "input[placeholder*='To' i]",
                    "input[aria-label*='To' i]",
                    "input[name*='destination' i]",
                    "input[id*='destination' i]",
                    "input[name*='to' i]",
                    "input[id*='to' i]",
                ],
                "BOM",
                interaction_log,
                "fill_destination",
            )
            destination_selected = destination_filled and await select_suggestion(
                page, ["BOM", "Mumbai"], interaction_log, "select_destination_suggestion"
            )

            report["booking_interaction"]["origin_selected"] = bool(origin_selected)
            report["booking_interaction"]["destination_selected"] = bool(destination_selected)

            date_opened = await click_first(
                page,
                [
                    "input[placeholder*='Depart' i]",
                    "input[aria-label*='Depart' i]",
                    "input[name*='depart' i]",
                    "input[id*='depart' i]",
                    "button:has-text('Departure')",
                    "text=/Departure/i",
                ],
                interaction_log,
                "open_departure_date",
            )
            date_selected = False
            if date_opened:
                date_selected = await click_first(
                    page,
                    [
                        "[aria-label*='September 12' i]",
                        "[aria-label*='Sep 12' i]",
                        "[aria-label*='12 September' i]",
                        "button:has-text('12')",
                        "text=/^\\s*12\\s*$/",
                    ],
                    interaction_log,
                    "select_departure_date",
                    timeout=3500,
                )
            report["booking_interaction"]["date_selected"] = bool(date_selected)

            report["booking_interaction"]["passenger_selected"] = True
            report["booking_interaction"]["currency_selected"] = "INR" in lower_text

            submitted = await click_first(
                page,
                [
                    "button:has-text('Search')",
                    "button:has-text('Search Flights')",
                    "[role='button']:has-text('Search')",
                    "text=/^\\s*search\\s*$/i",
                ],
                interaction_log,
                "submit_search",
                timeout=3500,
            )
            report["booking_interaction"]["search_submitted"] = bool(submitted)

            if submitted:
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except PlaywrightTimeoutError:
                    interaction_log.append({"step": "post_search_networkidle", "status": "timeout_continued"})
                await page.wait_for_timeout(5000)

            final_html = await page.content()
            final_text = summarize_visible_text(await page.locator("body").inner_text(timeout=5000))
            (ARTIFACT_DIR / "final.html").write_text(final_html, encoding="utf-8")
            (ARTIFACT_DIR / "final_visible_text.txt").write_text(final_text, encoding="utf-8")
            await page.screenshot(path=str(ARTIFACT_DIR / "final.png"), full_page=True)

            final_lower = f"{final_text}\n{final_html}".lower()
            report["browser"]["final_url"] = page.url
            report["results"]["results_page_reached"] = bool(submitted) and (
                "flight" in final_lower or "fare" in final_lower or "del" in final_lower or "bom" in final_lower
            )
            report["results"]["no_availability_visible"] = any(term in final_lower for term in NO_AVAILABILITY_TERMS)
            report["results"]["flight_card_count"] = await page.locator(
                "[data-testid*='flight' i], [class*='flight' i], [aria-label*='flight' i]"
            ).count()
            report["results"]["flight_number_visible"] = bool(re.search(r"\bAI[- ]?\d{2,4}\b", final_text, re.I))
            report["results"]["origin_destination_visible"] = "DEL" in final_text and "BOM" in final_text
            report["results"]["departure_arrival_visible"] = bool(re.search(r"\b\d{1,2}:\d{2}\b", final_text))
            report["results"]["total_fare_visible"] = bool(re.search(r"(?:INR|Rs\.?|₹)\s*[0-9][0-9,]*", final_text, re.I))
            report["results"]["fare_family_or_cabin_visible"] = any(
                term in final_lower for term in ["economy", "business", "flex", "value", "comfort", "cabin"]
            )
            report["results"]["base_fare_visible"] = "base fare" in final_lower
            report["results"]["taxes_fees_visible"] = any(term in final_lower for term in ["tax", "taxes", "fee", "fees"])
            report["results"]["visible_text_excerpt"] = final_text[:2000]

            report["blocking"]["captcha"] = any(term in final_lower for term in CAPTCHA_TERMS)
            report["blocking"]["bot_or_access_block"] = any(term in final_lower for term in BLOCK_TERMS)
            report["blocking"]["http_403_or_429"] = any(item["status"] in (403, 429) for item in response_statuses)
        except Exception as exc:
            report["browser"]["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            report["interaction_log"] = interaction_log
            report["console"] = console_messages[-30:]
            report["network"] = {
                "failed_requests": network_failures[-30:],
                "http_403_429": [item for item in response_statuses if item["status"] in (403, 429)][-30:],
                "status_sample": response_statuses[-40:],
            }
            await context.close()
            await browser.close()


def classify(report: dict) -> str:
    robots = report["robots"]
    if robots["result"] == "DISALLOWED":
        return "ROBOTS_DISALLOWED"
    if robots["result"] == "INCONCLUSIVE":
        return "INCONCLUSIVE"
    if report["blocking"]["captcha"] or report["blocking"]["bot_or_access_block"] or report["blocking"]["http_403_or_429"]:
        return "CAPTCHA_OR_BLOCK"
    if report["browser"].get("error"):
        return "NETWORK_OR_BROWSER_FAILURE"
    if report["results"]["no_availability_visible"] and report["booking_interaction"]["search_submitted"]:
        return "NO_AVAILABILITY"
    if (
        report["results"]["results_page_reached"]
        and report["results"]["flight_number_visible"]
        and report["results"]["departure_arrival_visible"]
        and report["results"]["total_fare_visible"]
    ):
        return "FEASIBLE"
    if not report["application_rendering"]["booking_form_visible"] or not report["booking_interaction"]["search_submitted"]:
        return "SEARCH_INTERACTION_FAILURE"
    return "INCONCLUSIVE"


async def main() -> None:
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target": TARGET,
        "database_before": db_counts(),
        "robots": {},
        "browser": {},
        "application_rendering": {},
        "booking_interaction": {
            "one_way_selected": False,
            "origin_selected": False,
            "destination_selected": False,
            "date_selected": False,
            "passenger_selected": False,
            "currency_selected": False,
            "search_submitted": False,
        },
        "results": {
            "results_page_reached": False,
            "flight_card_count": 0,
            "flight_number_visible": False,
            "origin_destination_visible": False,
            "departure_arrival_visible": False,
            "total_fare_visible": False,
            "fare_family_or_cabin_visible": False,
            "base_fare_visible": False,
            "taxes_fees_visible": False,
            "no_availability_visible": False,
        },
        "blocking": {
            "captcha": False,
            "bot_or_access_block": False,
            "http_403_or_429": False,
        },
        "interaction_log": [],
        "console": [],
        "network": {},
        "artifacts": [],
    }

    report["robots"] = await check_robots()
    if report["robots"]["result"] == "ALLOWED":
        await run_browser_diagnostic(report)

    report["database_after"] = db_counts()
    report["database_changed"] = report["database_before"] != report["database_after"]
    report["classification"] = classify(report)
    report["artifacts"] = sorted(p.name for p in ARTIFACT_DIR.iterdir() if p.is_file())
    (ARTIFACT_DIR / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
