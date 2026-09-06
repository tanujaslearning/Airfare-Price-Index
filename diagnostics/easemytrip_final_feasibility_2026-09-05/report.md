# EASEMYTRIP FINAL FEASIBILITY

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
- Production scraper created: none

## Final Result

- robots permission: INCONCLUSIVE
- results path: not reached
- public UI reachable: YES
- search interaction: FAIL
- results rendered: NO
- fare extraction: FAIL
- CAPTCHA/block: NO
- overall classification: NOT_FEASIBLE

The normal public booking page loaded, but the visible UI flow did not submit a search or navigate to a usable results/listing page. This was the second read-only diagnostic with the same practical outcome, so EaseMyTrip should not be promoted to a READY source.

## Robots

| Robots URL | Status | Timing | Relevant result |
|---|---:|---:|---|
| https://www.easemytrip.com/robots.txt | 200 | 381.73 ms | `/flights/` not explicitly disallowed; `/flight-search/listing*` explicitly disallowed |
| https://flight.easemytrip.com/robots.txt | 200 | 236.68 ms | no observed disallow for `/flightlist` |

Hostname/path findings:

- Booking form hostname: `www.easemytrip.com`
- Booking form path: `/flights/`
- Actual results hostname/path: not discoverable because the normal UI search did not submit/reach results
- Results path permission: INCONCLUSIVE

Permission is INCONCLUSIVE because the actual results path was not reached. The likely `www.easemytrip.com/flight-search/listing*` listing pattern is explicitly disallowed, but the diagnostic did not prove that this is the current normal-browser result path.

## Browser

- Playwright success: YES
- Browser version: 151.0.7922.34
- Booking HTTP status: 200
- Booking URL: https://www.easemytrip.com/flights/
- Page title: Cheap Flights, Flight Ticket Booking at Lowest Prices in India
- JavaScript rendering: YES
- Booking form visible: YES

Visible booking-page text included:

- `One-Way`
- `FROM`
- `[DEL]Indira Gandhi International Airport`
- `TO`
- `[BOM]Chhatrapati Shivaji International Airport`
- `DEPARTURE DATE`
- `TRAVELLER & CLASS`
- `1 Traveller`
- `Economy`
- `SEARCH`

## Interaction

- One-way selection: not changed; page already displayed one-way state
- Origin DEL selection: FAIL via stable visible input selectors
- Destination BOM selection: FAIL via stable visible input selectors
- Departure date 2026-09-06 selection: FAIL
- 1 adult / Economy: visible as page default
- Search submitted: NO

The browser remained on:

```text
https://www.easemytrip.com/flights/
```

## Results And Fare Visibility

- Results page reached: NO
- Final URL: https://www.easemytrip.com/flights/
- Final path: `/flights/`
- Flight-result cards: 0 genuine result cards
- Empty-results state: NO
- Route-unavailable state: NO
- Fare extraction attempted from genuine result cards: NO

Required fields available from genuine result cards:

- none

Fields not proven extractable:

- airline
- flight number
- departure time
- arrival time
- total fare
- cabin/fare family
- route
- departure date

Calendar fare hints and promotional/page text were not treated as flight quotes.

## Blocking

- CAPTCHA: NO
- Access blocked: NO
- 403/429 page: NO
- Bot challenge: NO
- Timeout: NO terminal browser failure

## Stable UI Anchors Observed

Observed stable or semantic booking-page anchors only:

- text: `One-Way`
- text: `FROM`
- text: `TO`
- text: `DEPARTURE DATE`
- text: `TRAVELLER & CLASS`
- text: `SEARCH`
- visible route text: `[DEL]Indira Gandhi International Airport`
- visible route text: `[BOM]Chhatrapati Shivaji International Airport`
- visible class text: `Economy`
- roles: `button`, `group`

No stable result-card selectors were observed because no results page rendered.

## Database

Before:

- raw total: 1951
- processed total: 1951
- LIVE raw: 61
- LIVE processed: 61
- MOCK raw: 1890
- MOCK processed: 1890
- scraping jobs: 32
- max scraping job id: 32
- index rows: 1

After:

- raw total: 1951
- processed total: 1951
- LIVE raw: 61
- LIVE processed: 61
- MOCK raw: 1890
- MOCK processed: 1890
- scraping jobs: 32
- max scraping job id: 32
- index rows: 1

Database changed: NO

## Artifacts

- `report.md`
- `report.json`
- `booking_page.png`
- `booking_page.html`
- `booking_page_visible_text.txt`
- `after_inputs.png`
- `after_inputs.html`
- `after_inputs_visible_text.txt`
- `results_page.png`
- `results_page.html`
- `results_page_visible_text.txt`
- `www_easemytrip_com_robots.txt`
- `flight_easemytrip_com_robots.txt`
- `run_diagnostic.py`

