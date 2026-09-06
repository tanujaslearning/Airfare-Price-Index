# Route Coverage Expansion Report - 2026-09-05

## Objective

Remove the DEL-BOM-only limitation from the daily LIVE collection workflow and prepare controlled expansion across the approved APIx prototype matrix.

No live collection was run during this planning phase. No production database rows were inserted, updated, or deleted.

## Production Files Inspected

- `backend/app/data/route_basket.py`
- `backend/app/data/live_source_readiness.py`
- `backend/app/db/seed.py`
- `backend/app/services/daily_collection_service.py`
- `backend/app/services/ingestion_service.py`
- `backend/app/services/live_index_service.py`
- `backend/app/services/index_engine.py`
- `backend/app/services/pipeline_service.py`
- `backend/app/api/v1/endpoints/routes.py`
- `backend/app/models/scraping_job.py`
- `scraper/base/source_orchestrator.py`
- `scraper/base/mock_scraper.py`
- `scraper/airlines/akasa_scraper.py`
- `scraper/scheduler/daily_scheduler.py`
- `frontend/src/pages/HomePage.tsx`
- `frontend/src/services/api.ts`
- `frontend/src/types/index.ts`

## Six Approved Routes

1. DEL-BOM
2. DEL-BLR
3. BOM-BLR
4. DEL-CCU
5. BLR-HYD
6. MAA-DEL

The approved route basket is now centralized in `backend/app/data/route_basket.py`.

## Five Approved Windows

1. T+1
2. T+7
3. T+15
4. T+30
5. T+45

The approved window list is now centralized in `backend/app/data/route_basket.py`.

## 30-Cell Target Matrix

The daily target matrix is:

```text
6 routes x 5 advance windows = 30 route-window combinations
```

Generated cells:

```text
DEL-BOM  x T+1, T+7, T+15, T+30, T+45
DEL-BLR  x T+1, T+7, T+15, T+30, T+45
BOM-BLR  x T+1, T+7, T+15, T+30, T+45
DEL-CCU  x T+1, T+7, T+15, T+30, T+45
BLR-HYD  x T+1, T+7, T+15, T+30, T+45
MAA-DEL  x T+1, T+7, T+15, T+30, T+45
```

## Architecture Verification

- Route configuration: PASS. Six routes are centrally represented.
- Window configuration: PASS. Five windows are centrally represented.
- Daily collection service: PASS. Defaults now target all approved routes and all approved windows unless a narrower supervised scope is provided.
- Route/window/source support: PASS. The daily runner now plans route-window cells and attempts ordered sources inside each cell.
- DEL-BOM hard-coding in daily workflow: PASS. Removed from daily route selection.
- Legacy `run_live_ingestion`: PASS. It now accepts a route_code parameter for approved routes while preserving existing callers.
- Source readiness: PASS. Only ready/default-enabled sources are attempted automatically.
- Scraping job model: PASS. Existing model can preserve source/route/window/status/provenance via job source_name and error_log without schema changes.
- Ingestion validation: PASS. Route, departure date, requested advance window, positive fare, LIVE mode, duplicate filtering, and job provenance remain enforced.
- Dashboard coverage calculation: PASS. LIVE coverage uses observed route-window combinations divided by 30, not quote count.
- MOCK/LIVE separation: PASS. Coverage joins processed quotes to raw LIVE provenance and excludes MOCK rows.

## Source Availability Per Route

| Route | First selected source | Current feasibility status | Safe to test next? | Notes |
|---|---|---|---|---|
| DEL-BOM | Akasa Air | VERIFIED_LIVE_DATA for T+1 | Yes, but already validated | 7 LIVE quotes collected in Job 21 for 2026-09-06 departure. |
| DEL-BLR | Akasa Air | NOT_TESTED_ROUTE | Yes, controlled test only | If Akasa route UI is unavailable, record ROUTE_UNAVAILABLE and do not retry repeatedly. |
| BOM-BLR | Akasa Air | NOT_TESTED_ROUTE | Yes, controlled test only | Same source readiness; route-specific support unproven. |
| DEL-CCU | Akasa Air | NOT_TESTED_ROUTE | Yes, controlled test only | Same source readiness; route-specific support unproven. |
| BLR-HYD | Akasa Air | NOT_TESTED_ROUTE | Yes, controlled test only | Same source readiness; route-specific support unproven. |
| MAA-DEL | Akasa Air | NOT_TESTED_ROUTE | Yes, controlled test only | Same source readiness; route-specific support unproven. |

Other sources:

| Source | Readiness | Default action |
|---|---|---|
| Akasa Air | READY | Permitted first source. |
| Air India | INCONCLUSIVE | Skip until feasibility/robots uncertainty is resolved. |
| SpiceJet | NO_AVAILABILITY | Skip for broad runs; do not hammer repeated no-availability cells. |
| IndiGo | SOURCE_NOT_FEASIBLE | Do not pursue. |
| Yatra | NOT_APPROVED_FOR_THIS_PHASE | Do not attempt. |

## Failover Logic

For each route-window cell:

1. Build the requested departure date from collection_date + advance_window_days.
2. Select sources in configured readiness order.
3. Skip sources that are not READY or not enabled by default.
4. Attempt the first permitted source through the existing compliant scraper.
5. If CAPTCHA, rate limit, access denied, temporary block, route unavailable, no availability, network failure, browser failure, or validation failure occurs, record the classification.
6. Continue to the next permitted ready source for that cell.
7. Stop the cell after the first VERIFIED_LIVE_DATA result.
8. If all sources are exhausted, preserve observations already collected elsewhere and report the cell outcome.

No source uses stealth, proxy rotation, private APIs, response replay, CAPTCHA solving, or mock fallback.

## Current LIVE Coverage

Collection date checked: 2026-09-05

- Expected LIVE route-window combinations: 30
- Observed LIVE route-window combinations: 1
- Coverage: 3.33%
- LIVE quote count in observed cells: 7
- Observed cell: DEL-BOM T+1
- Coverage interpretation: DEL-BOM T+1 with 7 quotes = 1 / 30, not 7 / 30
- Coverage status: INSUFFICIENT_COVERAGE
- Index value: not calculated

Database counts at end of planning phase:

- Raw total: 1909
- Processed total: 1909
- LIVE raw: 19
- LIVE processed: 19
- MOCK raw: 1890
- MOCK processed: 1890

These counts are unchanged by this planning phase.

## Recommended Next Controlled Live Tests

Do not run the full 30-cell matrix yet.

Recommended next approval batch:

```text
Akasa Air, T+1 only
DEL-BLR, departure 2026-09-06
BOM-BLR, departure 2026-09-06
DEL-CCU, departure 2026-09-06
BLR-HYD, departure 2026-09-06
MAA-DEL, departure 2026-09-06
```

DEL-BOM T+1 is already validated for this collection date and should not be repeated unless explicitly approving a full all-six T+1 batch.

If route-specific Akasa support fails for any of the five gap routes, classify ROUTE_UNAVAILABLE or the exact observed safety/technical status and stop retrying that route for Akasa.

## Tests

Backend:

```text
69 passed, 1 warning in 3.86s
```

Scraper:

```text
84 passed, 1 warning in 0.63s
```

Frontend build:

```text
passed
```

Vite emitted the existing chunk-size warning only.

## Database Changes

None in this planning phase.

No live jobs were created. No quotes were inserted. No mock data was generated. No indexes were calculated or persisted.
