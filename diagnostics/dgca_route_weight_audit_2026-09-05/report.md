# DGCA Route Weight Audit

Date: 2026-09-05

## Current Route-Weight Source

Route weights currently come from `routes.dgca_weight`, seeded in `backend/app/db/seed.py` as static percentages:

- DEL-BOM: 0.25
- DEL-BLR: 0.20
- BOM-BLR: 0.18
- DEL-CCU: 0.14
- BLR-HYD: 0.12
- MAA-DEL: 0.11

These values are not loaded from `dgca_reference_data`; the local `dgca_reference_data` table currently has 0 rows.

## Existing Official DGCA Values

Official DGCA city-pair passenger traffic is available from the previously investigated DGCA Table 5.01 artifact:

- Source: Directorate General of Civil Aviation
- Dataset: `TABLE 5.01 (INDIAN CITY-WISE PASSENGER TRAFFIC)`
- Period: 2024-25
- Format: PDF
- Reference: `https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/dataReports/aviationDataStatistics/airTransport/domestic/yearly/28/Normal/TABLE%205.01%20%28INDIAN%20CITY-WISE%20PASSENGER%20TRAFFIC%29.pdf`

The project should use this as a configuration/data-source layer, not as fabricated route percentages.

## Route Mapping

The six active prototype routes map to DGCA city-pair rows using the project's airport codes:

- DEL-BOM maps to DELHI-MUMBAI: AVAILABLE
- DEL-BLR maps to DELHI-BENGALURU: AVAILABLE
- BOM-BLR maps to MUMBAI-BENGALURU: AVAILABLE
- DEL-CCU maps to DELHI-KOLKATA: AVAILABLE
- BLR-HYD maps to BENGALURU-HYDERABAD: AVAILABLE
- MAA-DEL maps to CHENNAI-DELHI: AVAILABLE

Directionality must remain explicit because DGCA Table 5.01 provides `PASSENGERS TO CITY 2` and `PASSENGERS FROM CITY 2`.

## Proposed Data Structure

Create a code-level DGCA route-weight data source with records containing:

- `route_code`
- `origin`
- `destination`
- `dgca_route_identifier`
- `passenger_traffic`
- `traffic_period`
- `source`
- `source_reference`
- `directionality`
- `status`

Allowed statuses:

- `AVAILABLE`
- `MISSING`
- `NOT_MAPPED`

Weights should be calculated as:

`passenger_traffic(route) / sum(passenger_traffic(all AVAILABLE usable routes))`

Missing or unmapped routes must not receive arbitrary equal weights or fabricated zero weights.

## Files That Need Modification

- `backend/app/services/index_engine.py`
- `backend/app/api/v1/endpoints/routes.py`
- `backend/app/schemas/api_responses.py`
- `frontend/src/services/api.ts`
- `frontend/src/types/index.ts`
- `frontend/src/pages/HomePage.tsx`
- backend tests covering index aggregation and API schema

New files should hold the DGCA route-weight configuration and calculation service.

## Database Safety

No database migration is necessary. The foundation can be implemented as a configuration/data-source abstraction and API layer. Existing `apix.db` quote rows, index rows, and scraper jobs should not be modified.
