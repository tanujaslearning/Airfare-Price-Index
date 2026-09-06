# EASEMYTRIP FEASIBILITY

## Scope

- Source: EaseMyTrip
- Route: DEL-BOM
- Collection date: 2026-09-05
- Departure date: 2026-09-06
- Advance window: T+1
- Trip: one-way
- Passengers: 1 adult
- Cabin: Economy
- Database writes: none
- Scraping jobs created: none
- Daily collection workflow: not run

## Existing Architecture Fit

A future EaseMyTrip adapter should follow the existing source pattern:

- subclass `BaseFlightScraper`
- live under scraper source modules, preferably an OTA-specific module or `scraper/airlines/easemytrip_scraper.py` if keeping the current package layout
- use `verify_policy_and_rate_limit()` before public page access
- use normal Playwright visible UI interaction
- use `detect_block_or_captcha()` and stop on CAPTCHA/block signatures
- return `RawAirfareQuoteCreate` rows only after route/date/window/fare validation
- be added to `SOURCE_FACTORIES` and `LIVE_SOURCE_READINESS` only after feasibility is proven

The existing database already has EaseMyTrip as OTA source code `EMT`, but no production scraper was created in this diagnostic.

## Robots Permission

Overall robots permission: INCONCLUSIVE

Observed robots checks:

| URL | Status | Timing | Relevant rules | Result |
|---|---:|---:|---|---|
| https://www.easemytrip.com/robots.txt | 200 | 612.0 ms | `Disallow: /cheap_flights/`, `Disallow: /cheap-flights/`, `Disallow: /flight-search/listing*` | DISALLOWED for `/flight-search/listing*`; `/flights/` not disallowed |
| https://flight.easemytrip.com/robots.txt | 200 | 271.7 ms | `Disallow: /cheap_flights/`, `Disallow: /cheap-flights/` | No observed disallow for `/flightlist` |

Reason for INCONCLUSIVE:

The public booking page `/flights/` was reachable and not explicitly disallowed in the observed robots file, while one likely search/listing path on `www.easemytrip.com` is explicitly disallowed. Since this diagnostic did not successfully submit the search and confirm the actual result URL, a future parser must not assume that all flight-result paths are permitted.

## Public UI Reachability

- Public UI reachable: YES
- Playwright success: YES
- Browser version: 151.0.7922.34
- Page HTTP status: 200
- Final URL: https://www.easemytrip.com/flights/
- Page title: Cheap Flights, Flight Ticket Booking at Lowest Prices in India
- JavaScript rendering: YES
- CAPTCHA/block detected: NO
- ToS/access concern observed during page load: NO

Visible booking UI elements observed:

- One-Way
- Round-Trip
- Multi-City
- FROM
- `[DEL] Indira Gandhi International Airport`
- TO
- `[BOM] Chhatrapati Shivaji International Airport`
- DEPARTURE DATE
- TRAVELLER & CLASS
- 1 Traveller
- Economy
- SEARCH

## Search Interaction

Search interaction: FAIL

Observed interaction events:

- one_way_selector: `text=One-Way`
- from_selector: not found through stable input selectors
- from_option: `li:has-text('Delhi')`
- to_selector: not found through stable input selectors
- to_option: `div:has-text('Mumbai'):has-text('BOM')`
- date_selector: not found through stable input selectors
- date_option: not selected
- search_selector: not found

The page remained at:

```text
https://www.easemytrip.com/flights/
```

The diagnostic did not reach a flight-results page.

## Results Rendering

- Results rendered: NO
- Result-page URL: not reached
- Rendered flight cards: not confirmed
- Fare extraction: FAIL
- Sample parsed observations: none

The date picker/calendar did render fare hints after partial interaction, including visible values such as:

```text
6
Rs 6529
7
Rs 6095
12
Rs 6442
```

These are calendar fare hints, not validated flight-card observations. They were not inserted, parsed as quotes, or treated as verified LIVE data.

## Required Fields

Required fields available from the attempted result state:

- airline: partially visible in promotional/page content only, not tied to a flight card
- cabin class: visible as booking-form value
- route: visible as selected form fields
- total fare: visible as calendar fare hints only

Required fields unavailable as validated flight-card data:

- flight number
- departure time
- arrival time
- total fare tied to a specific flight card
- departure date tied to a specific flight card
- route tied to a specific flight card
- fare family

## Selectors And Page Elements

Stable page elements actually observed:

- text anchor: `One-Way`
- text anchor: `FROM`
- text anchor: `TO`
- text anchor: `DEPARTURE DATE`
- text anchor: `TRAVELLER & CLASS`
- text anchor: `SEARCH`
- visible route text: `[DEL] Indira Gandhi International Airport`
- visible route text: `[BOM] Chhatrapati Shivaji International Airport`
- visible cabin/traveller text: `1 Traveller`, `Economy`

No stable flight-result card selectors were observed because the results page was not reached. Generated CSS classes were not used as parser anchors.

## Blocking And Failures

- CAPTCHA: NO
- Access blocked: NO
- 403/429 page: NO
- Timeout: NO terminal browser timeout; some networkidle waits were bounded
- Empty results: not determined
- Unavailable route: not determined
- Unexpected page: YES, search did not transition away from the booking page
- Robots permission failure: INCONCLUSIVE due mixed path rules and unconfirmed result path

## Database Verification

Before:

- Raw total: 1951
- Processed total: 1951
- LIVE raw: 61
- LIVE processed: 61
- MOCK raw: 1890
- MOCK processed: 1890
- Scraping jobs: 32
- Max scraping job id: 32
- Index rows: 1

After:

- Raw total: 1951
- Processed total: 1951
- LIVE raw: 61
- LIVE processed: 61
- MOCK raw: 1890
- MOCK processed: 1890
- Scraping jobs: 32
- Max scraping job id: 32
- Index rows: 1

Database unchanged: YES

## Artifacts

Saved under `diagnostics/easemytrip_feasibility_2026-09-05/`:

- `report.json`
- `01_homepage.png`
- `02_after_inputs.png`
- `03_after_search.png`
- `homepage_excerpt.txt`
- `result_excerpt.txt`
- `network_summary.json`
- `console_messages.json`
- `www_easemytrip_com_robots.txt`
- `flight_easemytrip_com_robots.txt`

## Overall Classification

INCONCLUSIVE

Reason:

EaseMyTrip's public booking page loaded and rendered normally without CAPTCHA/blocking, but the controlled visible-UI interaction did not reach a results page and no validated flight-card data was exposed. Robots status is also not clean enough to call READY because a likely listing path is disallowed while another flight subdomain path appears not disallowed.

## Exact Next Recommended Action

Run one more read-only diagnostic only if the goal is to refine visible UI interaction selectors on the booking form and confirm the actual permitted result path. Do not create a production EaseMyTrip parser, do not add EaseMyTrip to READY source readiness, and do not use it for live ingestion until a read-only diagnostic reaches permitted rendered flight results with extractable flight-card fields.
