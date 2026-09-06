# Daily Collection Audit

Date: 2026-09-05

## Existing Reusable Pieces

- `BaseFlightScraper` already provides Playwright lifecycle, robots.txt checking, rate limiting, and CAPTCHA/block detection.
- `SourceOrchestrator` already passes explicit `advance_window_days` into source scrapers and classifies CAPTCHA, rate-limit, robots/access denial, and generic errors.
- Source-specific scrapers already support `fetch_quotes(..., departure_date, route_id, source_id, advance_window_days)`.
- `ingestion_service.validate_live_quote_contract` verifies route, departure date, requested advance window, and positive total fare before LIVE insertion.
- `ingestion_service.filter_duplicate_raw_quotes` prevents same-day duplicate LIVE quote insertion by route/source/flight/departure/window/mode/date.
- `process_raw_batch` can process only the inserted raw quotes for an attempt.
- `calculate_composite_index` already preserves `collection_mode` and now uses DGCA passenger-traffic weights.
- `calculate_live_only_index` can assess LIVE coverage without persisting an index.
- `scraping_job_logs` can be reused for per-attempt job status, quote count, timing, and error text.

## Current Gaps

- No daily collection service exists.
- `scraper/scheduler/__init__.py` is only a placeholder.
- No scheduler wiring exists for daily execution time, timezone, manual trigger, or graceful shutdown.
- Existing `run_live_ingestion` is hard-coded to DEL-BOM and a small source list; it is useful as prior art but not broad enough for route x window scheduling.
- `scraping_job_logs` does not have columns for route, advance window, collection date, or processed count. A migration is not required because detailed daily attempt records can be returned/logged by service dataclasses and encoded in job error/status messages when needed.

## Source Readiness

- Akasa Air: enabled/proven LIVE source.
- Air India: disabled for daily collection because readiness is INCONCLUSIVE.
- SpiceJet: disabled for daily collection because repeated DEL-BOM/DEL-BLR controlled tests produced NO_AVAILABILITY and should not be hammered.
- IndiGo: disabled because feasibility diagnostics classified it as not source-ready.
- Yatra: not pursued in this task.

## Route And Window Configuration

Active prototype routes come from the `routes` table:

- DEL-BOM
- DEL-BLR
- BOM-BLR
- DEL-CCU
- BLR-HYD
- MAA-DEL

Approved advance windows are already present as `[1, 7, 15, 30, 45]`.

## Date/Window Contract

The daily service must keep three dates/values distinct:

- `collection_date`: date the collection run is for
- `departure_date`: `collection_date + advance_window_days`
- `advance_window_days`: explicit requested booking window passed to the scraper

This prevents a requested T+1 observation from becoming T+0 because of scraper runtime clock behavior.

## Database And Migration Assessment

No migration is required for the daily collection foundation. Existing production quote/index data can be preserved while adding a service and scheduler wrapper.

## Files That Need Modification

- `backend/app/core/config.py`
- `backend/app/services/daily_collection_service.py`
- `scraper/scheduler/daily_scheduler.py`
- `scraper/scheduler/__init__.py`
- backend tests for daily collection and scheduler behavior
- final implementation report under `diagnostics/daily_collection_implementation_2026-09-05/report.md`
