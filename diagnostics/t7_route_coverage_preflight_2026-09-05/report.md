# T+7 Route Coverage Preflight - 2026-09-05

## Purpose

Prepare the next controlled LIVE validation batch for T+7 across all six approved APIx routes.

No live collection was executed. No scraping jobs were created. No database rows were inserted, updated, or deleted. No national index was recalculated.

## Requested Batch

- Collection date: 2026-09-05
- Advance window: T+7
- Expected departure date: 2026-09-12
- Collection mode for future approved run: LIVE
- Source priority: Akasa Air first; next permitted READY source only if Akasa cannot safely provide the route

## Route List

1. DEL-BOM
2. DEL-BLR
3. BOM-BLR
4. DEL-CCU
5. BLR-HYD
6. MAA-DEL

## Source Order

1. Akasa Air
   - source key: akasa
   - source code: QP
   - readiness status: READY
   - enabled by default: true
   - readiness reason: Proven controlled LIVE source for the prototype.

No other source is currently eligible as a READY default fallback:

- Air India: INCONCLUSIVE, disabled by default
- SpiceJet: NO_AVAILABILITY, disabled by default
- IndiGo: SOURCE_NOT_FEASIBLE, disabled by default

## Robots And Compliance Status

- Robots URL checked: https://www.akasaair.com/robots.txt
- Read-only fetch result: HTTP 403 through the preflight fetch path
- Preflight robots classification: INCONCLUSIVE
- Relevant public paths used by the existing Akasa scraper:
  - `/flight-booking`
  - `/flight-search`

Compliance guard status:

- The existing Akasa scraper calls `verify_policy_and_rate_limit()` before accessing both public booking/search URLs.
- The scraper uses normal Playwright browser interaction.
- CAPTCHA and block signatures are detected by `detect_block_or_captcha()`.
- No stealth plugins, proxy rotation, CAPTCHA solving, private API replay, or mock fallback are part of the collection path.

Safety note:

Because the preflight robots fetch returned 403, permission must not be assumed from this preflight alone. A future approved live run should rely on the existing runtime robots guard and must stop immediately if the guard classifies the path as disallowed or blocked.

## Expected Six Route-Window Cells

| Operation | Source | Route | Window | Collection date | Departure date |
|---:|---|---|---:|---|---|
| 1 | Akasa Air | DEL-BOM | 7 | 2026-09-05 | 2026-09-12 |
| 2 | Akasa Air | DEL-BLR | 7 | 2026-09-05 | 2026-09-12 |
| 3 | Akasa Air | BOM-BLR | 7 | 2026-09-05 | 2026-09-12 |
| 4 | Akasa Air | DEL-CCU | 7 | 2026-09-05 | 2026-09-12 |
| 5 | Akasa Air | BLR-HYD | 7 | 2026-09-05 | 2026-09-12 |
| 6 | Akasa Air | MAA-DEL | 7 | 2026-09-05 | 2026-09-12 |

The route-window target builder verifies:

```text
departure_date = collection_date + advance_window_days
2026-09-12 = 2026-09-05 + 7 days
```

## Current Database Counts

- Raw total: 1926
- Processed total: 1926
- LIVE raw: 36
- LIVE processed: 36
- MOCK raw: 1890
- MOCK processed: 1890
- Max scraping job id: 26
- Existing index row count: 1

## Current LIVE Coverage

For collection date 2026-09-05:

- Expected route-window combinations: 30
- Observed route-window combinations: 6
- Coverage: 20.0%
- Coverage status: INSUFFICIENT_COVERAGE
- Routes represented: 6
- Advance windows represented: 1
- Sources represented: Akasa Air
- Observed cells: all six routes at T+1

No T+7 cells are currently verified for this collection date.

## Proposed Future Command Scope

If explicitly approved later, run exactly:

```text
source_keys = ["akasa"]
route_codes = ["DEL-BOM", "DEL-BLR", "BOM-BLR", "DEL-CCU", "BLR-HYD", "MAA-DEL"]
advance_windows = [7]
collection_date = 2026-09-05
calculate_index_when_sufficient = False
```

Expected behavior:

1. Attempt each approved route once through Akasa Air.
2. Validate route, departure date 2026-09-12, advance_window_days 7, positive total fare, collection_mode LIVE, and scraping_job_id provenance.
3. Insert only valid LIVE raw quotes.
4. Process only inserted raw quotes.
5. Do not calculate or persist a national index.
6. Stop after these six T+7 cells.

## Preflight Result

Ready for explicit approval with one caveat:

- Route/window/date/source planning: PASS
- Database baseline recorded: PASS
- Current coverage recorded: PASS
- Source readiness from project config: PASS
- Robots preflight retrieval: INCONCLUSIVE due HTTP 403 from robots.txt URL

Recommendation:

Proceed only with explicit approval that the runtime collection must first pass the existing robots/rate-limit guard and must stop on any robots disallow, CAPTCHA, block, 403, 429, or other access-control issue.
