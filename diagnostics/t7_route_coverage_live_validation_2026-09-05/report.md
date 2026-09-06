# T+7 Route Coverage LIVE Validation - 2026-09-05

## Scope

- Collection date: 2026-09-05
- Departure date: 2026-09-12
- Advance window: T+7
- Source: Akasa Air only
- Routes attempted: DEL-BOM, DEL-BLR, BOM-BLR, DEL-CCU, BLR-HYD, MAA-DEL
- Collection mode: LIVE
- National index calculation: not run
- T+1 collection: not repeated
- T+15/T+30/T+45 collection: not run

## Database Before

- Raw total: 1926
- Processed total: 1926
- LIVE raw: 36
- LIVE processed: 36
- MOCK raw: 1890
- MOCK processed: 1890
- LIVE route-window coverage: 6 / 30, 20.0%
- Max scraping job id: 26
- Existing index row count: 1

## Per-Cell Results

| Route | Source | Job ID | Status | Classification | Raw inserted | Processed inserted | Reason |
|---|---|---:|---|---|---:|---:|---|
| DEL-BOM | Akasa Air | 27 | COMPLETED | VERIFIED_LIVE_DATA | 9 | 9 | duplicates_skipped=0 |
| DEL-BLR | Akasa Air | 28 | COMPLETED | VERIFIED_LIVE_DATA | 5 | 5 | duplicates_skipped=0 |
| BOM-BLR | Akasa Air | 29 | COMPLETED | VERIFIED_LIVE_DATA | 5 | 5 | duplicates_skipped=0 |
| DEL-CCU | Akasa Air | 30 | COMPLETED | VERIFIED_LIVE_DATA | 2 | 2 | duplicates_skipped=0 |
| BLR-HYD | Akasa Air | 31 | COMPLETED | VERIFIED_LIVE_DATA | 4 | 4 | duplicates_skipped=0 |
| MAA-DEL | Akasa Air | 32 | FAILED | CAPTCHA_OR_BLOCK | 0 | 0 | Akasa page timed out during normal public interaction |

Overall batch status: PARTIAL

The MAA-DEL T+7 cell stopped safely after the existing scraper/orchestrator classified the public interaction timeout as a temporary block path. No fallback source was forced because no other source is currently READY by default.

## Inserted T+7 Quotes

| Route | Job ID | Flight | Departure | Arrival | Fare | Mode |
|---|---:|---|---|---|---:|---|
| DEL-BOM | 27 | QP6520 | 2026-09-12 02:00 | 2026-09-12 04:15 | 6530.0 | LIVE |
| DEL-BOM | 27 | QP1833 | 2026-09-12 06:50 | 2026-09-12 09:10 | 6530.0 | LIVE |
| DEL-BOM | 27 | QP1119 | 2026-09-12 08:40 | 2026-09-12 11:05 | 6530.0 | LIVE |
| DEL-BOM | 27 | QP1112 | 2026-09-12 09:20 | 2026-09-12 11:40 | 6530.0 | LIVE |
| DEL-BOM | 27 | QP1110 | 2026-09-12 10:30 | 2026-09-12 12:45 | 6530.0 | LIVE |
| DEL-BOM | 27 | QP1836 | 2026-09-12 12:30 | 2026-09-12 14:55 | 6530.0 | LIVE |
| DEL-BOM | 27 | QP1128 | 2026-09-12 16:00 | 2026-09-12 18:20 | 6530.0 | LIVE |
| DEL-BOM | 27 | QP1820 | 2026-09-12 17:30 | 2026-09-12 19:45 | 6530.0 | LIVE |
| DEL-BOM | 27 | QP1826 | 2026-09-12 19:55 | 2026-09-12 22:20 | 6530.0 | LIVE |
| DEL-BLR | 28 | QP1308 | 2026-09-12 20:55 | 2026-09-12 23:50 | 8829.0 | LIVE |
| DEL-BLR | 28 | QP1350 | 2026-09-12 21:55 | 2026-09-12 00:50 | 8829.0 | LIVE |
| DEL-BLR | 28 | QP1812 | 2026-09-12 22:55 | 2026-09-12 01:45 | 8829.0 | LIVE |
| DEL-BLR | 28 | QP1822 | 2026-09-12 16:40 | 2026-09-12 19:40 | 9158.0 | LIVE |
| DEL-BLR | 28 | QP1824 | 2026-09-12 20:10 | 2026-09-12 23:10 | 9158.0 | LIVE |
| BOM-BLR | 29 | QP1518 | 2026-09-12 21:45 | 2026-09-12 23:45 | 7807.0 | LIVE |
| BOM-BLR | 29 | QP1133 | 2026-09-12 19:40 | 2026-09-12 21:45 | 9196.0 | LIVE |
| BOM-BLR | 29 | QP1382 | 2026-09-12 18:20 | 2026-09-12 20:20 | 10415.0 | LIVE |
| BOM-BLR | 29 | QP1527 | 2026-09-12 07:35 | 2026-09-12 09:35 | 11322.0 | LIVE |
| BOM-BLR | 29 | QP1516 | 2026-09-12 00:40 | 2026-09-12 02:35 | 12848.0 | LIVE |
| DEL-CCU | 30 | QP1801 | 2026-09-12 05:55 | 2026-09-12 08:15 | 7583.0 | LIVE |
| DEL-CCU | 30 | QP1803 | 2026-09-12 17:10 | 2026-09-12 19:25 | 8193.0 | LIVE |
| BLR-HYD | 31 | QP1409 | 2026-09-12 13:10 | 2026-09-12 23:10 | 17913.0 | LIVE |
| BLR-HYD | 31 | QP1406 | 2026-09-12 05:00 | 2026-09-12 16:45 | 18006.0 | LIVE |
| BLR-HYD | 31 | QP1406 | 2026-09-12 06:05 | 2026-09-12 16:45 | 18006.0 | LIVE |
| BLR-HYD | 31 | QP1406 | 2026-09-12 04:10 | 2026-09-12 16:45 | 18183.0 | LIVE |

## Validation Checks

- All inserted rows have collection_mode=LIVE.
- All inserted rows have departure date 2026-09-12.
- All inserted rows have advance_window_days=7.
- All inserted rows have positive total_fare.
- All inserted rows match the requested route for their job.
- All inserted rows preserve scraping_job_id provenance.
- Processed rows link back to raw LIVE rows for jobs 27-31.
- Job 32 inserted zero raw and zero processed rows.
- No T+1 rows were inserted by jobs 27-32.
- No non-LIVE rows were inserted by jobs 27-32.

## Database After

- Raw total: 1951
- Processed total: 1951
- LIVE raw: 61
- LIVE processed: 61
- MOCK raw: 1890
- MOCK processed: 1890
- LIVE route-window coverage: 11 / 30, 36.67%
- Existing index row count: 1

Coverage changed from 6/30 to 11/30 because five T+7 cells were verified. MAA-DEL T+7 remains unverified.

## Integrity Checks

- Pre-existing raw rows through id 1926 unchanged: yes
- Pre-existing processed rows through id 1926 unchanged: yes
- MOCK raw hash unchanged: yes
- Existing index row count unchanged: yes
- No national index was calculated or persisted.

## Tests

Command:

```powershell
$env:DEBUG='false'; .\.venv\Scripts\pytest.exe backend\tests\test_daily_collection.py backend\tests\test_live_index.py scraper\tests\test_akasa_scraper.py scraper\tests\test_source_orchestrator.py -q
```

Result:

```text
44 passed, 1 warning in 0.93s
```

## Final Status

The approved T+7 batch completed with partial success:

- VERIFIED_LIVE_DATA: 5 cells
- CAPTCHA_OR_BLOCK / temporary block timeout: 1 cell
- NO_AVAILABILITY: 0 cells
- Network/browser failure: 0 cells outside the classified timeout cell

No T+15, T+30, or T+45 work was started.
