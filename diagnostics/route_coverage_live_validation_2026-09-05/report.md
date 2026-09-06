# Route Coverage LIVE Validation - 2026-09-05

## Scope

- Approved batch: five untested T+1 route cells only
- Collection date: 2026-09-05
- Expected departure date: 2026-09-06
- Advance window: T+1
- Source priority: Akasa Air, then next permitted READY source if needed
- Actual source used: Akasa Air for all five cells
- DEL-BOM T+1: not repeated
- National index calculation: not run

## Database Before

- Raw total: 1909
- Processed total: 1909
- LIVE raw: 19
- LIVE processed: 19
- MOCK raw: 1890
- MOCK processed: 1890
- LIVE route-window coverage: 1 / 30, 3.33%
- Existing LIVE cell: DEL-BOM T+1
- Existing index row count: 1

## Batch Result

Overall status: COMPLETED

| Route | Source used | Job ID | Job status | Classification | Raw inserted | Processed inserted |
|---|---|---:|---|---|---:|---:|
| DEL-BLR | Akasa Air | 22 | COMPLETED | VERIFIED_LIVE_DATA | 5 | 5 |
| BOM-BLR | Akasa Air | 23 | COMPLETED | VERIFIED_LIVE_DATA | 5 | 5 |
| DEL-CCU | Akasa Air | 24 | COMPLETED | VERIFIED_LIVE_DATA | 2 | 2 |
| BLR-HYD | Akasa Air | 25 | COMPLETED | VERIFIED_LIVE_DATA | 4 | 4 |
| MAA-DEL | Akasa Air | 26 | COMPLETED | VERIFIED_LIVE_DATA | 1 | 1 |

Failure/no-availability classifications: none.

## Inserted Quotes

| Route | Job ID | Flight | Departure | Arrival | Fare | Window | Mode |
|---|---:|---|---|---|---:|---:|---|
| DEL-BLR | 22 | QP1812 | 2026-09-06 22:55 | 2026-09-06 01:45 | 13537.0 | 1 | LIVE |
| DEL-BLR | 22 | QP1350 | 2026-09-06 21:55 | 2026-09-06 00:50 | 14325.0 | 1 | LIVE |
| DEL-BLR | 22 | QP1308 | 2026-09-06 20:55 | 2026-09-06 23:50 | 15162.0 | 1 | LIVE |
| DEL-BLR | 22 | QP1824 | 2026-09-06 20:10 | 2026-09-06 23:10 | 15748.0 | 1 | LIVE |
| DEL-BLR | 22 | QP1822 | 2026-09-06 16:40 | 2026-09-06 19:40 | 17989.0 | 1 | LIVE |
| BOM-BLR | 23 | QP1133 | 2026-09-06 19:40 | 2026-09-06 21:45 | 7199.0 | 1 | LIVE |
| BOM-BLR | 23 | QP1516 | 2026-09-06 00:40 | 2026-09-06 02:23 | 8130.0 | 1 | LIVE |
| BOM-BLR | 23 | QP1527 | 2026-09-06 07:35 | 2026-09-06 09:35 | 8130.0 | 1 | LIVE |
| BOM-BLR | 23 | QP1518 | 2026-09-06 21:45 | 2026-09-06 23:45 | 9991.0 | 1 | LIVE |
| BOM-BLR | 23 | QP1382 | 2026-09-06 18:20 | 2026-09-06 20:20 | 10415.0 | 1 | LIVE |
| DEL-CCU | 24 | QP1801 | 2026-09-06 05:55 | 2026-09-06 08:15 | 8854.0 | 1 | LIVE |
| DEL-CCU | 24 | QP1803 | 2026-09-06 17:05 | 2026-09-06 19:25 | 9576.0 | 1 | LIVE |
| BLR-HYD | 25 | QP1406 | 2026-09-06 04:10 | 2026-09-06 16:45 | 17086.0 | 1 | LIVE |
| BLR-HYD | 25 | QP1406 | 2026-09-06 05:00 | 2026-09-06 16:45 | 17086.0 | 1 | LIVE |
| BLR-HYD | 25 | QP1406 | 2026-09-06 06:05 | 2026-09-06 16:45 | 17227.0 | 1 | LIVE |
| BLR-HYD | 25 | QP1409 | 2026-09-06 13:10 | 2026-09-06 23:10 | 20067.0 | 1 | LIVE |
| MAA-DEL | 26 | QP1120 | 2026-09-06 13:35 | 2026-09-06 21:15 | 19320.0 | 1 | LIVE |

One BLR-HYD processed quote was flagged as an outlier by the cleaning pipeline. It remains correctly stored as a processed LIVE quote, but LIVE coverage/index analytics exclude outliers.

## Database After

- Raw total: 1926
- Processed total: 1926
- LIVE raw: 36
- LIVE processed: 36
- MOCK raw: 1890
- MOCK processed: 1890
- LIVE route-window coverage: 6 / 30, 20.0%
- Existing index row count: 1

## Verification

- collection_mode=LIVE for all 17 inserted raw quotes.
- Processed rows link back to raw LIVE provenance for all 17 inserted quotes.
- scraping_job_id provenance preserved for jobs 22, 23, 24, 25, and 26.
- departure_date=2026-09-06 for all 17 inserted raw quotes.
- advance_window_days=1 for all 17 inserted raw and processed rows.
- All inserted route codes match the approved requested routes.
- All inserted total_fare values are greater than 0.
- DEL-BOM was not repeated in jobs 22-26.
- MOCK raw hash unchanged.
- Pre-existing raw rows through id 1909 unchanged.
- Pre-existing processed rows through id 1909 unchanged.
- No existing rows were deleted or modified.
- No national index was recalculated or persisted.

## Tests

Command:

```powershell
$env:DEBUG='false'; .\.venv\Scripts\pytest.exe backend\tests\test_daily_collection.py backend\tests\test_live_index.py scraper\tests\test_akasa_scraper.py scraper\tests\test_source_orchestrator.py -q
```

Result:

```text
44 passed, 1 warning in 1.06s
```

## Final Status

The approved five-cell T+1 expansion completed successfully.

The project now has LIVE T+1 observations for all six approved routes:

```text
DEL-BOM
DEL-BLR
BOM-BLR
DEL-CCU
BLR-HYD
MAA-DEL
```

No T+7, T+15, T+30, or T+45 collections were run.
