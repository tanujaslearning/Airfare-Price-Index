# Live Website Collection

## Scope

The live collection layer keeps the existing APIx architecture intact. Mock mode remains the offline demo path, while live mode routes one controlled website collection through the same raw quote, cleaning, normalization, and index calculation pipeline.

Current Phase 1 source:

- Air India public website page: `https://www.airindia.com/en-in/book-flights/`
- Controlled route/window: `DEL-BOM`, `T+7`
- Output contract: `RawAirfareQuoteCreate`

## Ethical Safeguards

The scraper uses the existing `BaseFlightScraper` infrastructure:

- checks `robots.txt` before requesting the target page
- applies the per-domain async rate limiter
- uses a normal Playwright browser context
- detects CAPTCHA, hCaptcha, reCAPTCHA, Turnstile, Cloudflare challenge text, HTTP 403, HTTP 429, access denied, and rate-limit pages
- stops on block events and does not attempt bypass

The scraper does not use stealth plugins, proxy rotation, private APIs, login sessions, cookies, payment pages, or CAPTCHA solving.

## Live vs Mock Mode

`SCRAPER_MODE=mock`

- uses `MockFlightScraper`
- generates the existing synthetic matrix
- remains suitable for offline tests and dashboard demos

`SCRAPER_MODE=live`

- uses `SourceOrchestrator`
- attempts `AirIndiaWebsiteScraper`
- does not silently fall back to mock data
- returns a clear failed pipeline response if no live source can collect quotes

## Source Failover and Cooldown

`SourceOrchestrator` keeps ordered source priority and simple in-memory health:

- `AVAILABLE`
- `SUCCESS`
- `TEMPORARILY_BLOCKED`
- `CAPTCHA`
- `RATE_LIMITED`
- `ACCESS_DENIED`
- `ERROR`

When a source is blocked or errors, it is placed in cooldown and skipped for the current collection cycle. In Phase 1, Air India is the only live source, so the orchestrator reports that no live fallback source is configured.

## Extracted Fields

Air India visible fare cards may provide only route, date, cabin label, and total fare. When base fare or taxes are not visibly available, the scraper records:

- `base_fare=0.0`
- `taxes_fees=0.0`
- actual visible `total_fare`

The existing cleaning service then applies the project's established missing-component handling. Missing flight number and arrival time remain `None`.

## Controlled Live Run

Use a tiny live run only:

```powershell
$env:DEBUG="True"
$env:SCRAPER_MODE="live"
.\.venv\Scripts\python.exe -c "import asyncio; from datetime import date; from backend.app.db.session import SessionLocal; from backend.app.services.pipeline_service import run_full_live_pipeline; db=SessionLocal(); print(asyncio.run(run_full_live_pipeline(db, collection_date=date.today()))); db.close()"
```

Do not run bulk collection until the first source is proven reliable and compliant.

## DGCA Backtest Requirements

The repository does not currently contain the 30-day DGCA monthly average-fare reference dataset needed for backtesting. To satisfy that requirement later, add official DGCA route/month reference fares into the existing `dgca_reference` layer, then compare daily APIx-derived route averages with the monthly reference by route and period. Useful metrics would include absolute error, percentage error, route coverage, observed quote count, and missing-route count.
