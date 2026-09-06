# Yatra Feasibility Report

Date: 2026-09-05

## Target

- Source: Yatra
- Route: DEL-BOM
- Collection date: 2026-09-05
- Departure date: 2026-09-06
- Requested window: T+1
- Trip: one-way
- Passengers: 1 adult
- Currency: INR

## GitHub Reference Inspection

Repository inspected:

- https://github.com/vishal815/Python-Based-Flight-Data-Scraping-Automating-Data-Collection-for-Analysis

The repository is historical evidence only. No CSV data was copied and no selectors were adopted without current-page validation.

Observed workflow from `Yatra.ipynb`:

- Uses Selenium WebDriver with a locally hard-coded ChromeDriver executable path.
- Opens a prebuilt Yatra results URL directly:
  - `https://flight.yatra.com/air-search-ui/int2/trigger?...`
- Uses a fixed `time.sleep(29)` to wait for dynamic content.
- Reads `driver.page_source`, closes the browser, then parses HTML with BeautifulSoup.
- Detects flight rows using `div.airline-holder.clearfix`.
- Extracts:
  - airline name
  - departure time
  - departure airport
  - arrival time
  - arrival airport
  - duration
  - stops
  - price
- Price extraction uses a broad `p.i-b` element with an `id`, then strips non-digits.

Limitations of the old implementation:

- Does not use the normal public booking UI; it jumps directly to a generated results URL.
- Does not check robots.txt, rate limits, CAPTCHA, or blocking.
- Uses fixed sleeps instead of rendered-state checks.
- Uses brittle generated/class-heavy selectors.
- Does not validate route/date/window integrity before accepting rows.
- Does not preserve source/job provenance.
- Does not handle no-availability versus technical failure cleanly.
- Original example targets an international route/date, not the current APIx DEL-BOM T+1 target.

## Robots Status

Primary local diagnostic:

- Robots URL: `https://www.yatra.com/robots.txt`
- HTTP status: not received
- Timing: 12618.1 ms
- Result: INCONCLUSIVE
- Error: `ReadTimeout`

Additional bounded local checks:

- `https://www.yatra.com/robots.txt`: timed out after 15 seconds
- `https://flight.yatra.com/robots.txt`: timed out after 15 seconds

External browser-research observation:

- `https://www.yatra.com/robots.txt` was reachable externally.
- Observed `User-agent: *` with `Allow: /`.
- Observed explicit disallows including `/fresco/`, `/pwa/`, and `/pwa`.

Compliance decision:

- The local APIx diagnostic environment could not reliably retrieve robots.txt for the relevant hosts.
- Because the existing compliance posture does not assume permission when robots is unreliable, no Yatra booking UI interaction was performed.
- Direct use of the historical `flight.yatra.com/air-search-ui/.../trigger` URL was not attempted.

## Page Accessibility

- Public Yatra page load: not attempted.
- Reason: robots/access remained locally inconclusive.
- Playwright browser interaction: not attempted beyond diagnostic preparation.

## Search Interaction Result

- One-way selection: not attempted.
- Origin DEL: not attempted.
- Destination BOM: not attempted.
- Departure date 2026-09-06: not attempted.
- Passenger 1 adult: not attempted.
- Currency INR: not attempted.
- Search submitted: no.

## CAPTCHA / Block Result

- CAPTCHA observed: no.
- Bot challenge observed: no.
- 403/429 observed: no.
- Blocking classification: none observed.
- The diagnostic stopped due to robots/access inconclusiveness, not due to CAPTCHA or a browser block.

## Result Page URL

- No result page reached.
- No Yatra search URL was generated through the public UI.
- No private/internal API, response replay, or direct result URL collection was used.

## Result-Card Structure

Current Yatra result-card structure was not validated because the public UI search was not performed.

Historical repository selectors observed but not adopted:

- `div.airline-holder.clearfix`
- `div.full.mb-8.fs-13.airline-name`
- `div.i-b.col-4.no-wrap.text-right.dtime`
- `div.i-b.col-5.pdd-0.text-left.atime`
- `p.fs-12.bold.du.mb-2`
- `span[ng-class="{'dotted-borderbtm':leg.stops>0}"]`
- `p.i-b[id]`

## Stable Selectors / Anchors

No current Yatra UI anchors were validated.

Do not use the historical class selectors for a production parser until a current public UI diagnostic reaches rendered results.

## Fields Available

No current rendered fields were observed.

Historically, the old notebook attempted to extract:

- airline
- departure time
- departure airport
- arrival time
- arrival airport
- duration
- stops
- price

## Fields Unavailable

Unavailable in this diagnostic because no current search results were reached:

- displayed date
- airline
- flight number
- origin/destination
- departure/arrival time
- duration
- stops
- total fare
- fare family
- base fare
- taxes/fees

## Sample Parsed Observations

None.

No data was parsed from Yatra and no production database rows were inserted.

## Database Verification

Before:

- Raw total: 2172
- Processed total: 2172
- LIVE raw: 12
- LIVE processed: 12
- Latest scraping job ID: 20

After:

- Raw total: 2172
- Processed total: 2172
- LIVE raw: 12
- LIVE processed: 12
- Latest scraping job ID: 20

Database changed: no.

## Parser Feasibility Classification

INCONCLUSIVE

Reason:

- Historical Selenium/BeautifulSoup evidence exists, but current Yatra parser readiness was not proven.
- Local robots access for `www.yatra.com` and `flight.yatra.com` timed out.
- Current public UI interaction and current rendered result-card structure were not validated.

## Exact Next Recommended Action

Run one read-only Yatra robots/access diagnostic later, limited to reliable retrieval of:

- `https://www.yatra.com/robots.txt`
- `https://flight.yatra.com/robots.txt`

Only if the relevant public booking and result paths are confirmed allowed should APIx perform a single public-UI Playwright search for DEL-BOM T+1. Do not build a Yatra parser or run ingestion until current rendered results expose extractable fare cards through compliant public UI access.
