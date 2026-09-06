# Daily Collection LIVE Validation - 2026-09-05

## Scope

- Source: Akasa Air
- Route: DEL-BOM
- Advance window: T+1
- Collection date: 2026-09-05, from configured Asia/Kolkata date
- Departure date: 2026-09-06
- Trip: one-way
- Passengers: 1 adult
- Currency: INR
- Collection mode: LIVE
- Collection attempts run: 1
- Index calculation: not run

## Preflight Verification

- Configured timezone: Asia/Kolkata
- Verified departure date: 2026-09-06 = collection date 2026-09-05 + 1 day
- Verified advance_window_days: 1
- Verified collection_mode: LIVE
- Akasa source: id 4, code QP, name Akasa Air
- DEL-BOM route: id 1

## Database Before

- Raw total: 1902
- Processed total: 1902
- LIVE raw: 12
- LIVE processed: 12
- MOCK raw: 1890
- MOCK processed: 1890
- Existing LIVE raw IDs: 1891-1902
- Existing index rows: 1

## Live Run Result

- Job ID: 21
- Job source_name: DailyLive:Akasa Air:DEL-BOM:T+1
- Job status: COMPLETED
- Classification: VERIFIED_LIVE_DATA
- Raw rows inserted: 7
- Processed rows inserted: 7
- Duplicates skipped: 0
- CAPTCHA/blocking: none reported
- Private APIs, stealth, proxy rotation, CAPTCHA bypass: not used

## Inserted LIVE Quotes

| raw_id | flight_number | departure | arrival | advance_window_days | total_fare | collection_mode | scraping_job_id |
|---:|---|---|---|---:|---:|---|---:|
| 1903 | QP1119 | 2026-09-06 08:40 | 2026-09-06 11:05 | 1 | 6530.0 | LIVE | 21 |
| 1904 | QP1112 | 2026-09-06 09:20 | 2026-09-06 11:40 | 1 | 6530.0 | LIVE | 21 |
| 1905 | QP1110 | 2026-09-06 10:30 | 2026-09-06 12:45 | 1 | 6530.0 | LIVE | 21 |
| 1906 | QP1820 | 2026-09-06 17:30 | 2026-09-06 19:45 | 1 | 7686.0 | LIVE | 21 |
| 1907 | QP1826 | 2026-09-06 19:55 | 2026-09-06 22:20 | 1 | 8739.0 | LIVE | 21 |
| 1908 | QP1836 | 2026-09-06 12:30 | 2026-09-06 14:55 | 1 | 8899.0 | LIVE | 21 |
| 1909 | QP1128 | 2026-09-06 16:00 | 2026-09-06 18:20 | 1 | 10134.0 | LIVE | 21 |

## Database After

- Raw total: 1909
- Processed total: 1909
- LIVE raw: 19
- LIVE processed: 19
- MOCK raw: 1890
- MOCK processed: 1890
- Existing LIVE raw IDs 1891-1902 preserved: yes
- Job 21 raw rows with collection_mode LIVE: 7
- Job 21 processed rows linked to LIVE raw rows: 7
- Job 21 rows with non-LIVE collection_mode: 0
- Job 21 departure/window check: 7 rows at departure_date 2026-09-06 and advance_window_days 1
- Existing index rows after run: 1

## Tests

Command:

```powershell
$env:DEBUG='false'; .\.venv\Scripts\pytest.exe backend\tests\test_daily_collection.py scraper\tests\test_akasa_scraper.py scraper\tests\test_source_orchestrator.py -q
```

Result:

```text
28 passed, 1 warning in 0.36s
```

Earlier validation before the live run:

```text
backend/tests: 62 passed, 1 warning
scraper/tests: 84 passed, 1 warning
frontend build: passed
```

## Verification Summary

- collection_mode persisted as LIVE for all inserted raw quotes.
- scraping_job_id provenance preserved as 21 for all inserted raw quotes and linked processed rows.
- advance_window_days persisted as 1 for every inserted quote.
- departure date persisted as 2026-09-06 for every inserted quote.
- MOCK counts unchanged.
- Pre-existing LIVE rows were not modified or deleted.
- No index was calculated or persisted during this validation.
