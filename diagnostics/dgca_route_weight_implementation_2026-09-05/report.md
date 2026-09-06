# DGCA Route Weight Implementation Report

Date: 2026-09-05

## Files Changed

- `diagnostics/dgca_route_weight_audit_2026-09-05/report.md`
- `backend/app/data/__init__.py`
- `backend/app/data/dgca_route_weights.py`
- `backend/app/services/dgca_route_weights.py`
- `backend/app/services/index_engine.py`
- `backend/app/services/live_index_service.py`
- `backend/app/api/v1/endpoints/routes.py`
- `backend/app/schemas/api_responses.py`
- `backend/app/schemas/index.py`
- `backend/tests/test_api_v1.py`
- `backend/tests/test_index_engine.py`
- `frontend/src/services/api.ts`
- `frontend/src/types/index.ts`
- `frontend/src/pages/HomePage.tsx`
- `frontend/src/components/RouteCorridorCard.tsx`
- `frontend/tsconfig.app.tsbuildinfo`
- `frontend/tsconfig.node.tsbuildinfo`
- `frontend/dist/index.html`
- `frontend/dist/assets/index-DLyL3x5w.css`
- `frontend/dist/assets/index-a6ooHk8F.js`

## DGCA Source Used

- Source: Directorate General of Civil Aviation
- Dataset: `TABLE 5.01 (INDIAN CITY-WISE PASSENGER TRAFFIC)`
- Period: 2024-25
- Format: PDF
- Source reference: `https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/dataReports/aviationDataStatistics/airTransport/domestic/yearly/28/Normal/TABLE%205.01%20%28INDIAN%20CITY-WISE%20PASSENGER%20TRAFFIC%29.pdf`

No DGCA airfare data was used or fabricated.

## Routes Successfully Mapped

All six prototype routes have available DGCA passenger-traffic mappings in the new configuration layer:

- DEL-BOM: DELHI-MUMBAI, directional, passenger traffic 3426228
- DEL-BLR: BENGALURU-DELHI, directional, passenger traffic 2350018
- BOM-BLR: BENGALURU-MUMBAI, directional, passenger traffic 2083737
- DEL-CCU: DELHI-KOLKATA, directional, passenger traffic 1417339
- BLR-HYD: BENGALURU-HYDERABAD, directional, passenger traffic 1153136
- MAA-DEL: CHENNAI-DELHI, directional, passenger traffic 1222119

## Routes Missing Or Unmapped

- Missing routes: none among the six approved prototype routes
- Unmapped routes: none among the six approved prototype routes

The service supports `MISSING` and `NOT_MAPPED` statuses for future routes without assigning fabricated weights.

## Weight Calculation Methodology

Weights are calculated from official DGCA passenger traffic only:

`weight(route) = passenger_traffic(route) / sum(passenger_traffic(AVAILABLE usable routes))`

Routes without valid official passenger traffic are excluded from the denominator. No equal-weight fallback or silent zero-weight substitution is used for national aggregation.

For observed national index aggregation, route sub-indexes are calculated normally, then DGCA weights are applied and renormalized over observed routes only:

`National APIx = sum(route_index * DGCA_route_weight) / sum(observed_route_weights)`

MOCK and LIVE collection modes remain separated by the existing `collection_mode` filters.

## API Endpoint

Added:

`GET /api/v1/routes/weights`

The endpoint returns:

- source
- traffic period
- directionality
- route-level passenger traffic
- normalized DGCA weight
- status
- coverage summary
- missing routes
- unmapped routes

Existing route and route-index responses now expose DGCA weights from the new service instead of relying on the legacy `routes.dgca_weight` values.

## Frontend Changes

The dashboard now calls `GET /api/v1/routes/weights`.

DGCA route weight displays now show:

- normalized DGCA weight when `AVAILABLE`
- `Not available` when `MISSING`
- `Not mapped` when `NOT_MAPPED`

React no longer formats the legacy route table percentages as authoritative DGCA weights.

## Tests And Results

Backend tests:

`DEBUG=false pytest backend/tests -q`

Result: 55 passed, 1 warning.

Scraper tests:

`DEBUG=false pytest scraper/tests -q`

Result: 84 passed, 1 warning.

Frontend build:

`npm.cmd run build`

Result: passed. Vite emitted a non-failing chunk-size warning for the bundled JS asset.

## Database Changes

No database rows were inserted, updated, or deleted.

Post-implementation database check:

- raw total: 1902
- processed total: 1902
- LIVE raw: 12
- LIVE processed: 12
- MOCK raw: 1890
- MOCK processed: 1890
- `dgca_reference_data` rows: 0
- persisted index rows: one original MOCK row for 2026-09-04 with value 101.1

No migration was created or run.

## LIVE National Index Readiness

The national LIVE index is now ready for DGCA-weighted aggregation when sufficient LIVE route/window observations exist.

Current blocker remains LIVE coverage, not weighting infrastructure. Existing LIVE observations remain untouched, and no live collection was performed.

## Remaining Blockers

- DGCA official public airfare data remains unavailable for a true 30-day airfare backtest.
- `dgca_reference_data` still models average fare, but no official DGCA average-fare data has been found or loaded.
- The legacy `routes.dgca_weight` column still exists for schema compatibility; production aggregation and dashboard display now use the new DGCA route-weight service instead.
