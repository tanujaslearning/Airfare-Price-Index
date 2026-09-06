# Phase 4 Audit Report: Real Data Pipeline Integration

Audit date: 2026-09-05  
Project path: `C:\Users\TANUJA R\OneDrive\Desktop\airfare`  
Scope: read-only code and database inspection. No live scraping was run. No database tables or production code were modified.

## A. Current Architecture

The project is a local monorepo with four active layers:

- `backend/`: FastAPI app, SQLAlchemy models, Pydantic schemas, data pipeline services, index services, REST endpoints.
- `scraper/`: mock data generator plus direct airline website scrapers for Akasa Air, Air India, and SpiceJet.
- `frontend/`: React + TypeScript + Vite dashboard using Axios calls into the FastAPI API.
- `apix.db`: current local SQLite runtime database in the project root.

Runtime database configuration:

- `backend/app/core/config.py` defaults to `USE_SQLITE_FALLBACK=True`.
- `backend/.env` explicitly sets `DATABASE_URL="sqlite:///./apix.db"` and `USE_SQLITE_FALLBACK=True`.
- No project-root `.env` exists.
- No `backend/apix.db` exists.
- The inspected runtime DB is therefore the project-root `apix.db` when the backend is run from the project root. The configured path is relative, so starting the backend from a different working directory could point at a different `./apix.db`.

Pipeline flow currently implemented:

1. Scraper emits `RawAirfareQuoteCreate`.
2. `ingest_raw_quotes()` persists rows into `raw_airfare_quotes`, stamping `collection_mode` and optional `scraping_job_id`.
3. `process_raw_batch()` normalizes raw rows into `processed_airfare_quotes`.
4. `calculate_composite_index()` computes and persists a national index row in `airfare_index_values`.
5. Dashboard reads latest/historical index rows plus route-level computed breakdowns.

Live mode selection:

- `/api/v1/pipeline/trigger` checks `settings.SCRAPER_MODE`.
- Default `SCRAPER_MODE` is `"mock"`.
- `SCRAPER_MODE="live"` runs `run_full_live_pipeline()`.
- Current controlled live code path is route-limited to `DEL-BOM` and defaults to `advance_window_days=7`.
- `run_live_ingestion()` currently constructs `SourceOrchestrator(sources=[AkasaWebsiteScraper(), AirIndiaWebsiteScraper()])`; SpiceJet is present as a scraper module but is not in this default live pipeline source list.

## B. Database State

Database engine inspected: SQLite, `apix.db`.

Alembic version:

| version_num |
|---|
| `b6f8c2d4a901` |

Table counts:

| table | rows |
|---|---:|
| `airlines` | 6 |
| `routes` | 6 |
| `raw_airfare_quotes` | 1902 |
| `processed_airfare_quotes` | 1902 |
| `scraping_job_logs` | 14 |
| `airfare_index_values` | 1 |
| `dgca_reference_data` | 0 |

Tables actually used at runtime:

- `airlines`: source/carrier dimension.
- `routes`: route dimension and DGCA weights.
- `raw_airfare_quotes`: raw observations with source, route, fare, mode, and job provenance.
- `processed_airfare_quotes`: normalized quote layer used by index calculations.
- `scraping_job_logs`: ingestion/job audit log.
- `airfare_index_values`: persisted national index time series.
- `dgca_reference_data`: defined, currently empty, not used by the current baseline implementation.
- `alembic_version`: migration tracking.

Raw quote fields in runtime schema:

| field | type | notes |
|---|---|---|
| `id` | INTEGER | primary key |
| `source_id` | INTEGER nullable | FK to `airlines.id` |
| `route_id` | INTEGER | FK to `routes.id` |
| `flight_number` | VARCHAR(30) nullable | indexed |
| `departure_datetime` | DATETIME | indexed |
| `arrival_datetime` | DATETIME nullable | optional |
| `advance_window_days` | INTEGER | indexed |
| `base_fare` | FLOAT | non-null, default/model value `0.0` |
| `taxes_fees` | FLOAT | non-null, default/model value `0.0` |
| `total_fare` | FLOAT | indexed, required |
| `cabin_class` | VARCHAR(30) | default/model value `ECONOMY` |
| `scraped_at` | DATETIME | indexed |
| `collection_mode` | VARCHAR(10) | indexed, DB default `'MOCK'` |
| `scraping_job_id` | INTEGER nullable | FK to `scraping_job_logs.id`, indexed |

Processed quote fields:

| field | type | notes |
|---|---|---|
| `id` | INTEGER | primary key |
| `raw_quote_id` | INTEGER nullable | FK to raw quote |
| `route_id` | INTEGER | FK to route |
| `advance_window_days` | INTEGER | indexed |
| `clean_total_fare` | FLOAT | indexed, required |
| `is_outlier` | BOOLEAN | indexed |
| `processed_at` | DATETIME | indexed |

Scraping job fields:

| field | type | notes |
|---|---|---|
| `id` | INTEGER | primary key |
| `source_name` | VARCHAR(100) | indexed |
| `status` | VARCHAR(30) | `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `BLOCKED` by convention |
| `total_scraped` | INTEGER | job-level count |
| `start_time` | DATETIME | required |
| `end_time` | DATETIME nullable | completion timestamp |
| `error_log` | TEXT nullable | failure details |

Source fields:

- `airlines.id`
- `airlines.code`
- `airlines.name`
- `airlines.is_ota`
- `airlines.created_at`

Current sources:

| id | code | name | is_ota |
|---:|---|---|---:|
| 1 | `6E` | IndiGo Airlines | 0 |
| 2 | `AI` | Air India | 0 |
| 3 | `SG` | SpiceJet | 0 |
| 4 | `QP` | Akasa Air | 0 |
| 5 | `MMT` | MakeMyTrip | 1 |
| 6 | `EMT` | EaseMyTrip | 1 |

Route fields:

- `routes.id`
- `routes.origin_code`
- `routes.destination_code`
- `routes.distance_km`
- `routes.dgca_weight`
- `routes.is_active`
- `routes.created_at`

Current active routes:

| id | route | distance_km | dgca_weight |
|---:|---|---:|---:|
| 1 | DEL-BOM | 1148.0 | 0.25 |
| 2 | DEL-BLR | 1740.0 | 0.20 |
| 3 | BOM-BLR | 842.0 | 0.18 |
| 4 | DEL-CCU | 1305.0 | 0.14 |
| 5 | BLR-HYD | 502.0 | 0.12 |
| 6 | MAA-DEL | 1757.0 | 0.11 |

Advance-window representation:

- Stored directly as integer `advance_window_days` on raw and processed quote rows.
- Standard windows come from `scraper.base.mock_scraper.ADVANCE_WINDOWS`: `1`, `7`, `15`, `30`, `45`.
- UI labels are rendered as `T+{advance_window_days}`.
- Live ingestion guard allows only `{1, 7, 15, 30, 45}`, but the default live pipeline call does not expose the requested window through the API trigger.

Collection mode and provenance:

- `raw_airfare_quotes.collection_mode` is the authoritative runtime field for `LIVE` vs `MOCK`.
- `processed_airfare_quotes` does not denormalize `collection_mode`; it must be joined back to `raw_airfare_quotes`.
- `scraping_job_id` exists only on raw quotes, then remains reachable from processed rows through `processed_airfare_quotes.raw_quote_id`.

Raw quote totals:

| metric | count |
|---|---:|
| total raw quotes | 1902 |
| total processed quotes | 1902 |
| LIVE raw quotes | 12 |
| MOCK raw quotes | 1890 |
| LIVE processed quotes | 12 |
| MOCK-linked processed quotes | 1890 |
| unprocessed raw quotes | 0 |
| processed rows with missing raw link | 0 |

Processed outliers:

| collection_mode | processed | outliers | usable |
|---|---:|---:|---:|
| LIVE | 12 | 0 | 12 |
| MOCK | 1890 | 21 | 1869 |

Raw provenance summary:

| collection_mode | source | scraping_job_id | quote_count |
|---|---|---:|---:|
| LIVE | Akasa Air | 11 | 7 |
| LIVE | Akasa Air | 13 | 5 |
| MOCK | Air India | null | 420 |
| MOCK | Akasa Air | null | 420 |
| MOCK | IndiGo Airlines | null | 630 |
| MOCK | SpiceJet | null | 420 |

Important provenance gap:

- All 1890 current MOCK raw rows have `scraping_job_id = NULL`.
- There are seven completed `MockSyntheticEngine` jobs with `total_scraped=270` each, but the current mock quote rows are not linked to those jobs.
- The 12 LIVE rows are linked to jobs 11 and 13.

## C. Live Data State

LIVE raw quotes by source:

| source | raw quotes | first_scraped_at | last_scraped_at |
|---|---:|---|---|
| Akasa Air | 12 | 2026-09-04 10:00:00.000000 | 2026-09-04 16:22:57.688272 |

LIVE raw quotes by route:

| route | raw quotes |
|---|---:|
| DEL-BOM | 12 |

LIVE raw quotes by advance window:

| advance_window_days | raw quotes |
|---:|---:|
| 1 | 5 |
| 7 | 7 |

LIVE processed usable coverage:

| route | window | processed | outliers | usable | mean usable fare |
|---|---:|---:|---:|---:|---:|
| DEL-BOM | 1 | 5 | 0 | 5 | 6530.00 |
| DEL-BOM | 7 | 7 | 0 | 7 | 7571.71 |

Current live Akasa records:

| job_id | route | window | raw quotes | mean total | min total | max total | zero base/tax |
|---:|---|---:|---:|---:|---:|---:|---:|
| 13 | DEL-BOM | 1 | 5 | 6530.00 | 6530.00 | 6530.00 | 5 |
| 11 | DEL-BOM | 7 | 7 | 7571.71 | 6530.00 | 11124.00 | 6 |

Current live Akasa details:

- Job 11: 7 DEL-BOM T+7 quotes, scraped at `2026-09-04 16:22:57.688272`, departure date `2026-09-11`.
- Job 13: 5 DEL-BOM T+1 validation quotes, scraped at `2026-09-04 10:00:00.000000`, departure date `2026-09-05`.
- 11 of 12 Akasa live rows have `base_fare=0.0` and `taxes_fees=0.0` with positive `total_fare`.
- One Akasa live row, `QP1833`, has visible/enriched components: `base_fare=5640.0`, `taxes_fees=890.0`, `total_fare=6530.0`.

Current SpiceJet state:

- `scraper/airlines/spicejet_scraper.py` exists and emits `source_name="SpiceJet"`.
- The SpiceJet parser sets `base_fare=0.0` and `taxes_fees=0.0` for parsed visible result rows while preserving `total_fare`.
- There are no persisted LIVE SpiceJet raw quotes in `apix.db`.
- There are no `scraping_job_logs.source_name LIKE '%Spice%'` rows.
- There is one failed `LiveWebsiteOrchestrator` job whose error log references SpiceJet:
  - Job 14, status `FAILED`, start `2026-09-05 05:47:42.242446`, end `2026-09-05 05:48:03.215567`, `total_scraped=0`.
  - Error: `SpiceJet: ERROR: No visible SpiceJet fare cards found for DEL-BOM on 2026-09-05; SourceOrchestrator: ERROR: SpiceJet unavailable; no live fallback source configured.`

## D. Mock Data State

Current mock raw rows:

| source | raw quotes | zero base/tax positive total |
|---|---:|---:|
| Air India | 420 | 0 |
| Akasa Air | 420 | 0 |
| IndiGo Airlines | 630 | 0 |
| SpiceJet | 420 | 0 |

MOCK route/window raw coverage:

- All six routes have all five standard windows.
- Each route/window has 63 raw mock quotes.
- Total matrix coverage: 30 of 30 route-window combinations.
- Current mock source density by route: Air India 70, Akasa Air 70, IndiGo 105, SpiceJet 70 per route.

MOCK rows are not linked to scraping jobs:

| collection_mode | scraping_job_id | quote_count |
|---|---:|---:|
| MOCK | null | 1890 |

## E. Coverage Matrix

Expected Phase 4 route-window grid:

- Routes: 6 active routes.
- Windows: 5 standard windows.
- Total expected combinations: 30.

LIVE route x window coverage, raw quote counts:

| route | T+1 | T+7 | T+15 | T+30 | T+45 | observed windows |
|---|---:|---:|---:|---:|---:|---:|
| DEL-BOM | 5 | 7 | 0 | 0 | 0 | 2/5 |
| DEL-BLR | 0 | 0 | 0 | 0 | 0 | 0/5 |
| BOM-BLR | 0 | 0 | 0 | 0 | 0 | 0/5 |
| DEL-CCU | 0 | 0 | 0 | 0 | 0 | 0/5 |
| BLR-HYD | 0 | 0 | 0 | 0 | 0 | 0/5 |
| MAA-DEL | 0 | 0 | 0 | 0 | 0 | 0/5 |

LIVE coverage summary:

| metric | value |
|---|---:|
| expected route-window combinations | 30 |
| observed LIVE route-window combinations | 2 |
| LIVE coverage percent | 6.67% |
| routes represented | 1/6 |
| windows represented | 2/5 |
| sources represented | 1 |

MOCK route x window coverage, raw quote counts:

| route | T+1 | T+7 | T+15 | T+30 | T+45 | observed windows |
|---|---:|---:|---:|---:|---:|---:|
| DEL-BOM | 63 | 63 | 63 | 63 | 63 | 5/5 |
| DEL-BLR | 63 | 63 | 63 | 63 | 63 | 5/5 |
| BOM-BLR | 63 | 63 | 63 | 63 | 63 | 5/5 |
| DEL-CCU | 63 | 63 | 63 | 63 | 63 | 5/5 |
| BLR-HYD | 63 | 63 | 63 | 63 | 63 | 5/5 |
| MAA-DEL | 63 | 63 | 63 | 63 | 63 | 5/5 |

Latest scraping job per job source name:

| source_name | latest_job_id | status | total_scraped | start_time | end_time |
|---|---:|---|---:|---|---|
| Akasa Air T+1 Validation | 13 | COMPLETED | 5 | 2026-09-05 03:31:33.447158 | 2026-09-05 03:31:56.894258 |
| LiveWebsiteOrchestrator | 14 | FAILED | 0 | 2026-09-05 05:47:42.242446 | 2026-09-05 05:48:03.215567 |
| MockSyntheticEngine | 7 | COMPLETED | 270 | 2026-09-04 11:30:46.046354 | 2026-09-04 11:30:47.208896 |

Successful jobs:

| job ids | count | total_scraped |
|---|---:|---:|
| 1, 2, 3, 4, 5, 6, 7, 11, 13 | 9 | 1902 |

Failed jobs:

| job_id | source_name | total_scraped | failure category |
|---:|---|---:|---|
| 8 | LiveWebsiteOrchestrator | 0 | Playwright browser executable missing for Air India |
| 9 | LiveWebsiteOrchestrator | 0 | Playwright browser executable missing for Air India |
| 10 | LiveWebsiteOrchestrator | 0 | Air India `ERR_HTTP2_PROTOCOL_ERROR` |
| 12 | LiveWebsiteOrchestrator | 0 | Akasa no visible cards, Air India `ERR_HTTP2_PROTOCOL_ERROR` |
| 14 | LiveWebsiteOrchestrator | 0 | SpiceJet no visible fare cards |

## F. Index Methodology Currently Implemented

Persisted index path:

- Implemented in `backend/app/services/index_engine.py`.
- `get_route_baseline_fare(route_key, advance_window)` uses static in-code route baselines and static advance-window multipliers.
- Baseline formula: `route_base * window_multiplier + 21% tax approximation + 650`.
- Route-window sub-index formula: `(mean clean_total_fare / baseline_fare) * 100`.
- Route index: arithmetic mean of observed window sub-indices for that route.
- National composite: DGCA-weighted mean of route indices over routes observed on the calculation date.
- Persisted output is written to `airfare_index_values`.

Critical implementation detail:

- `calculate_route_indices()` filters on `ProcessedAirfareQuote.is_outlier == False` and `processed_at` date.
- It does not filter by `RawAirfareQuote.collection_mode`.
- If no rows match by `processed_at`, it falls back to linked `RawAirfareQuote.scraped_at` date, still without filtering `collection_mode`.
- Therefore, the persisted index calculation can mix MOCK and LIVE rows when both are processed for the same target date.

Current stored index row:

| id | date | frequency | index_value | baseline_period | ma_7d | ma_30d | dod_change_pct | calculated_at |
|---:|---|---|---:|---|---:|---:|---:|---|
| 1 | 2026-09-04 | daily | 101.1 | 2026-Q1 | 101.1 | 101.1 | null | 2026-09-04 16:23:16.340529 |

Read-only recomputation for 2026-09-04:

| scope | recomputed composite | included usable quotes | route-window coverage |
|---|---:|---:|---|
| ALL processed rows | 100.97 | 1881 | 30/30 |
| MOCK-linked only | 101.10 | 1869 | 30/30 |
| LIVE-linked only | 84.62 | 12 | 2/30 |

Interpretation:

- The stored value `101.1` matches the mock-only recomputation after rounding.
- The code path that produced it can still mix MOCK and LIVE because there is no mode guard.
- The low live-only DEL-BOM T+1 value would slightly lower an all-data recompute, but the mock dataset dominates because it has 1869 usable rows versus 12 live rows.

Live-only index path:

- Implemented in `backend/app/services/live_index_service.py`.
- Exposed via `GET /api/v1/index/live`.
- Joins processed quotes back to raw quotes and filters `RawAirfareQuote.collection_mode == "LIVE"`.
- Does not persist results.
- Requires 100% observed route-window coverage within the requested scope before returning a non-null `index_value`.
- With no filters, current LIVE coverage is 2/30, so it should return `INSUFFICIENT_COVERAGE` and `index_value=null`.
- With `route_code=DEL-BOM`, current LIVE coverage is 2/5, so it should also be insufficient.
- With `route_code=DEL-BOM&advance_window_days=1` or `7`, coverage would be sufficient within that narrow scope.

Base fare and taxes issue:

- `SpiceJetWebsiteScraper.extract_quotes_from_text()` sets `base_fare=0.0` and `taxes_fees=0.0` when parsing visible fares.
- `AkasaWebsiteScraper.extract_quotes_from_text()` also starts rows with `base_fare=0.0` and `taxes_fees=0.0`; only the first quote may be enriched from the fare summary.
- `AirIndiaWebsiteScraper` uses zero components when component labels are unavailable.
- The cleaning service checks whether `base_fare + taxes_fees == total_fare`; if not, and `total_fare > 0`, it derives an approximate component split in memory.
- `ProcessedAirfareQuote` stores only `clean_total_fare`, not the derived component split.

Could `base_fare=0.0` and `taxes_fees=0.0` incorrectly affect index calculations?

- Current total-fare APIx calculation: no, not directly. The index uses `ProcessedAirfareQuote.clean_total_fare`, which is derived from raw `total_fare`.
- Current outlier detection: no direct component effect; it uses `clean_total_fare`.
- Current data-quality/provenance interpretation: yes. Zero components encode "unknown" as if it were an actual zero value. Any future component-level metric, tax validation, fare breakdown chart, or quality rule could misinterpret unknown base/tax as real zero.
- Current SpiceJet DB state: no live SpiceJet rows exist, and the 420 mock SpiceJet rows do not use zero components.

## G. API/Dashboard Status

Current API endpoints:

| method | path | status/use |
|---|---|---|
| GET | `/` | root service overview |
| GET | `/api/health` | service health |
| GET | `/api/v1/index/latest` | reads latest persisted `airfare_index_values` row |
| GET | `/api/v1/index/historical` | reads persisted index history |
| GET | `/api/v1/index/live` | live-only non-persisted analysis |
| GET | `/api/v1/routes` | active/all route list |
| GET | `/api/v1/routes/{route_code}/index` | route/window breakdown from processed quotes |
| POST | `/api/v1/pipeline/trigger` | runs mock or live pipeline depending on `SCRAPER_MODE` |
| GET | `/api/v1/provenance/summary` | raw quote provenance grouped by mode/source/job |
| GET | `/api/v1/provenance/live-summary` | live-only processed aggregate summary |
| GET | `/api/v1/provenance/jobs` | completed/failed jobs with mode |
| GET | `/api/v1/provenance/live-quotes` | live-only raw quote list |

Dashboard data flow:

- `frontend/src/services/api.ts` exposes calls for health, latest index, historical index, routes, route index, and pipeline trigger.
- `frontend/src/pages/HomePage.tsx` refreshes the dashboard by calling:
  - `getLatestIndex()`
  - `getHistoricalIndex({ frequency: "daily", limit })`
  - `getRoutes(true)`
  - `getRouteIndex(routeCode)` for selected route and route summaries
- `triggerPipeline()` posts to `/api/v1/pipeline/trigger`, then refreshes the same persisted-index dashboard data.
- The dashboard does not currently call `/api/v1/index/live` or any `/api/v1/provenance/*` endpoints.
- Some dashboard text/labels say "Live Data", but the displayed latest/historical index and route breakdowns come from mixed-capable persisted/processed endpoints, not live-only endpoints.

Route endpoint caveat:

- `/api/v1/routes/{route_code}/index` does not filter by `collection_mode`.
- For missing windows, it returns baseline fare and `sub_index=100.0` with `quotes_count=0`.
- It computes `route_index` from observed windows only.
- Historical route points currently repeat the current route index for each distinct historical date rather than recomputing per date.

## H. Data-Quality Risks

1. Persisted index can mix MOCK and LIVE data.

`calculate_composite_index()` has no mode filter and `airfare_index_values` has no `collection_mode` column. A future live run on a day with mock rows can produce a mixed national index without making that visible in the persisted index table or dashboard.

2. Dashboard "Live Data" wording is not backed by live-only data calls.

The main dashboard uses `/api/v1/index/latest`, `/api/v1/index/historical`, and `/api/v1/routes/{route}/index`, all of which read persisted or processed data without mode filtering.

3. Unknown base/tax components are encoded as numeric zero.

SpiceJet, Akasa, and Air India parsers can use `0.0` for unavailable base/tax components. This does not currently alter total-fare index math, but it is a semantic data-quality risk and could break component-level analysis later.

4. Processed quotes lack denormalized provenance fields.

`processed_airfare_quotes` has no `collection_mode`, `source_id`, or `scraping_job_id`. This is recoverable by joining raw rows today, but it makes accidental unfiltered calculations easy and complicates audit queries.

5. Mock job provenance is incomplete.

All 1890 mock rows have `scraping_job_id=NULL`, even though mock jobs exist with matching total counts. This weakens batch traceability and makes exact job-to-row lineage impossible for current mock data.

6. Live coverage is far below national-index sufficiency.

Current live data covers only DEL-BOM T+1 and T+7. National live coverage is 2/30 route-window combinations, or 6.67%.

7. Live pipeline source configuration and diagnostics diverge.

The default live pipeline lists Akasa and Air India. SpiceJet diagnostics and a failed job exist, but SpiceJet is not in the default `run_live_ingestion()` source list in `backend/app/services/ingestion_service.py`.

8. Relative SQLite path can cause environment drift.

`sqlite:///./apix.db` depends on backend process working directory. This can silently create or read a different DB if launched from `backend/` or another directory.

9. DGCA reference table is empty.

The current index does not use official `dgca_reference_data`; it uses static in-code baseline fares and multipliers.

10. Duplicate/mock accumulation can dominate live data.

There are seven mock ingestions worth of data in the current DB. Even when live rows exist for the same date, they are numerically overwhelmed by mock rows unless mode filters are applied.

## I. Recommended Changes

1. Make index mode explicit.

Add `collection_mode` to persisted index outputs and index APIs, or create separate persisted tables/records for `LIVE` and `MOCK`. The national/dashboard default for Phase 4 should be live-only and should report insufficient coverage instead of falling back to mock.

2. Add mode filters to index and route calculations.

Update `calculate_route_indices()`, `calculate_composite_index()`, and `/api/v1/routes/{route_code}/index` to accept and apply `collection_mode`, joining to raw quote provenance when needed.

3. Surface coverage explicitly in the dashboard.

Display live route-window coverage, expected combinations, observed combinations, and whether the live index is sufficient. Use `/api/v1/index/live` and provenance endpoints for live panels.

4. Represent unknown fare components as unknown.

Change future raw/component schema semantics so unknown `base_fare` and `taxes_fees` are nullable or accompanied by a component quality/status field such as `fare_components_available=false`. Avoid using `0.0` as a sentinel for unknown.

5. Preserve processed provenance.

Either denormalize `collection_mode`, `source_id`, and `scraping_job_id` into `processed_airfare_quotes`, or enforce all processed-query entry points through helper functions that always join raw provenance.

6. Separate demo/mock reset from real ingestion.

Keep mock data available for UI demos, but isolate it from live pipeline runs through either separate DBs, a `dataset_id`, or explicit mode-scoped API defaults.

7. Make the SQLite path absolute in local config.

Use an absolute SQLite URL for local development or derive it from the project root to avoid accidental DB drift.

8. Add source-specific live readiness gates.

Before adding a source to default live ingestion, require a parser test, a controlled validation job, component availability status, duplicate policy, and route/window support declaration.

## J. Exact Next Implementation Step

Implement a mode-scoped index contract before ingesting more real data:

1. Add `collection_mode` to `airfare_index_values` through an Alembic migration and SQLAlchemy/Pydantic schema updates.
2. Update `calculate_route_indices()` and `calculate_composite_index()` to require or accept `collection_mode`, joining `processed_airfare_quotes` to `raw_airfare_quotes` and filtering on `RawAirfareQuote.collection_mode`.
3. Update `/api/v1/index/latest`, `/api/v1/index/historical`, and `/api/v1/routes/{route_code}/index` to accept `collection_mode`, defaulting Phase 4 dashboard usage to `LIVE`.
4. Keep `/api/v1/index/live` as the non-persisted coverage gate, but make the persisted index path impossible to mix modes.
5. Add tests proving MOCK and LIVE rows on the same date produce separate index results and that dashboard-facing endpoints do not mix them.

This is the first implementation step because the current largest Phase 4 risk is not the SpiceJet zero-component sentinel; it is that the main persisted index and dashboard-facing route calculations can blend synthetic and real observations without visible provenance.
