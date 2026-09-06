# HappyFares Controlled Feasibility Diagnostic

- Source: HappyFares
- Route: DEL-BOM
- Collection date: 2026-09-06
- Database modified: False
- Robots result: ALLOWED
- Total usable observations: 0

## Robots

| Target | Robots URL | Result | Elapsed | Detail |
|---|---|---:|---:|---|
| https://www.happyfares.in/ | https://www.happyfares.in/robots.txt | ALLOWED | 2411 ms | RobotFileParser.can_fetch returned true |
| https://www.happyfares.in/flights | https://www.happyfares.in/robots.txt | ALLOWED | 2253 ms | RobotFileParser.can_fetch returned true |
| https://www.happyfares.in/flight-search | https://www.happyfares.in/robots.txt | ALLOWED | 2056 ms | RobotFileParser.can_fetch returned true |

## Attempts

| Window | Departure | Status | Quotes | Final URL | Error |
|---:|---|---|---:|---|---|
| T+1 | 2026-09-07 | TIMEOUT | 0 |  | Timeout 15000ms exceeded.
=========================== logs ===========================
"load" event fired
============================================================ |
| T+7 | 2026-09-13 | TIMEOUT | 0 |  | Stopped after T+1 status TIMEOUT; no bypass or retry attempted. |
| T+15 | 2026-09-21 | TIMEOUT | 0 |  | Stopped after T+1 status TIMEOUT; no bypass or retry attempted. |
| T+30 | 2026-10-06 | TIMEOUT | 0 |  | Stopped after T+1 status TIMEOUT; no bypass or retry attempted. |
| T+45 | 2026-10-21 | TIMEOUT | 0 |  | Stopped after T+1 status TIMEOUT; no bypass or retry attempted. |

## Database Counts

- Before: {'raw_total': 1951, 'processed_total': 1951, 'live_raw': 61, 'live_processed': 61, 'mock_raw': 1890, 'mock_processed': 1890}
- After: {'raw_total': 1951, 'processed_total': 1951, 'live_raw': 61, 'live_processed': 61, 'mock_raw': 1890, 'mock_processed': 1890}

## Recommendation

Do not add HappyFares to production source readiness unless a later approved diagnostic proves usable structured fare observations through robots-allowed public UI paths.