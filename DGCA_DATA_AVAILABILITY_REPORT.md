# DGCA Data Availability Report

Date: 2026-09-05

Scope: read-only research into official DGCA / Government of India sources that could support APIx validation, weighting, and comparison with airfare trends.

No APIx database changes, mock-data generation, index calculation, or methodology changes were performed.

## Executive Summary

DGCA publishes useful official aviation traffic and operating statistics, especially passenger counts, airline market share, load factor, aircraft/seat-kilometre operating metrics, and annual city-pair passenger traffic.

I did not find an official public DGCA dataset that publishes realized average airfare by route, airline, sector, or day. DGCA and the Ministry of Civil Aviation publicly describe tariff monitoring and airline route-wise fare sheets, but those sources describe monitoring/compliance and airline-published fare buckets, not a downloadable DGCA public time series of actual paid fares or daily route average fares.

For APIx:

- DGCA can support route weighting and airline market-share weighting.
- DGCA can support coarse validation against monthly/annual traffic, capacity, load-factor, OTP, cancellation, and complaint trends.
- DGCA cannot support a true 30-consecutive-day airfare backtest from official public data found in this investigation.

## Official Source Inventory

### 1. DGCA Aviation Data & Statistics Portal

- Official source URL: `https://www.dgca.gov.in/digigov-portal/`
- Navigation observed: DGCA site map lists `Data and Reports > Aviation Data & Statistics > Air Transport`.
- Relevant sections observed:
  - Civil Aviation Statistics Handbook
  - Domestic Air Transport
  - Domestic Air Transport > Air Traffic
  - Domestic Air Transport > Monthly Statistics
  - Domestic Air Transport > Annual Statistics
  - International Air Transport > Quarterly Statistics
- Data format: portal HTML plus downloadable PDFs hosted under official public DGCA S3 inventory.
- Update frequency: mixed; monthly for domestic traffic/airline reports, annual for handbook/yearly tables, quarterly for international air transport.
- Variables/columns: depends by report; passenger traffic, aircraft departures/hours/km, passenger-km, available seat-km, passenger load factor, cargo/freight/mail, tonne-km, available tonne-km, weight load factor, airline market share, cancellations, complaints, OTP.
- Route granularity: annual city-pair passenger traffic appears available; monthly route-level domestic fare data was not found.
- Airline granularity: available in monthly and annual airline operating statistics.
- Actual airfare present: not found.
- Passenger/traffic data present: yes.
- Revenue present: not found in the domestic monthly traffic PDFs checked; some older annual fleet/personnel/financial OGD catalog metadata references financial/revenue-related statistics, but not route/date airfare.
- Average fare can legitimately be calculated: no, not from the identified DGCA passenger/traffic tables alone.
- APIx weighting support: yes, especially route/city-pair passenger weights and airline market-share/passenger weights.
- 30-day backtest support: no, not for fare levels.
- Limitations: DGCA portal is dynamic; many records are PDFs, not tidy CSV; current-page enumeration may require manual portal navigation.

Official source evidence:

- DGCA site map exposes the Aviation Data & Statistics sections.
- DGCA portal footer states the site content is managed and owned by the Directorate General of Civil Aviation.

### 2. Domestic Air Transport - Air Traffic Reports

- Official source URL pattern:
  - `https://www.dgca.gov.in/digigov-portal/?page=jsp/dgca/InventoryList/dataReports/aviationDataStatistics/airTransport/domestic/airTraffic/...`
- Confirmed official S3 examples:
  - `https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/dataReports/aviationDataStatistics/airTransport/domestic/airTraffic/June2022.pdf`
  - `https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/dataReports/aviationDataStatistics/airTransport/domestic/airTraffic/Traffic%20report%20dec%2023.pdf`
- Data format: PDF.
- Time coverage: monthly reports; confirmed examples for June 2022 and December 2023. Current DGCA portal/search results also expose 2026 domestic traffic reporting.
- Update frequency: monthly.
- Variables/columns: domestic airlines passenger totals, market share, passenger load factor, OTP at major airports, cancellations, delays, passenger complaints and related operational summaries.
- Route granularity: no route/city-pair fare granularity found in these monthly air-traffic reports.
- Airline granularity: yes.
- Actual airfare present: no realized fare or average-fare table found.
- Passenger/traffic data present: yes.
- Revenue present: no route/airline revenue table found in the inspected domestic traffic reports.
- Average fare can legitimately be calculated: no.
- APIx weighting support: yes for airline weights and market-share context.
- 30-day backtest support: not feasible for airfare; monthly traffic only.
- Limitations: PDF format; airline-level rather than route-window-level; not a price source.

### 3. Domestic Air Transport - Monthly Statistics / Airline Operating Statistics

- Official source URL pattern:
  - `https://www.dgca.gov.in/digigov-portal/?page=monthlyStatistics/...`
  - Official S3 examples under `InventoryList/dataReports/aviationDataStatistics/airTransport/domestic/monthly/`
- Confirmed official S3 examples:
  - `https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/dataReports/aviationDataStatistics/airTransport/domestic/monthly/india%20one%20air22.pdf`
  - `https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/dataReports/aviationDataStatistics/airTransport/domestic/monthly/indigo22.pdf`
- Data format: PDF.
- Time coverage: monthly/annualized airline operating-statistics files; confirmed 2022 examples. OGD metadata for similar monthly traffic/operating statistics covers older series as well.
- Update frequency: monthly or fiscal-year grouped monthly tables, depending on report.
- Variables/columns: aircraft flown/departures, hours, kilometres, passengers carried, passenger-kilometres performed, available seat-kilometres, passenger load factor, cargo/freight/mail, tonne-kilometres, available tonne-kilometres, weight load factor.
- Route granularity: no; airline-month granularity.
- Airline granularity: yes.
- Actual airfare present: no.
- Passenger/traffic data present: yes.
- Revenue present: not in the identified monthly operating-statistics fields.
- Average fare can legitimately be calculated: no.
- APIx weighting support: yes for airline weights, capacity/load-factor context, and source coverage plausibility.
- 30-day backtest support: not feasible for airfare; monthly operating data only.
- Limitations: not route-specific; no fare or route-window data.

### 4. Civil Aviation Statistics Handbook

- Official source URL pattern:
  - `https://www.dgca.gov.in/digigov-portal/?page=jsp/dgca/InventoryList/dataReports/aviationDataStatistics/handbookCivilAviation/...`
- Confirmed official S3 examples:
  - `https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/dataReports/aviationDataStatistics/handbookCivilAviation/HANDBOOK%202024-25.pdf`
  - `https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/dataReports/aviationDataStatistics/handbookCivilAviation/HANDBOOK%202023-24%20Final%20Draft.pdf`
- Data format: PDF handbook.
- Time coverage: annual fiscal-year handbook; confirmed 2023-24 and 2024-25 PDFs.
- Update frequency: annual.
- Variables/columns: consolidated civil aviation statistics, including passenger traffic, operating statistics, fleet/personnel/airport/city-pair style tables depending on section.
- Route granularity: annual city/city-pair tables exist in the yearly/handbook structure.
- Airline granularity: annual airline operating-statistics tables exist.
- Actual airfare present: no public average airfare table found.
- Passenger/traffic data present: yes.
- Revenue present: not identified as a route/airline fare series. Older government open-data catalog metadata references financial/revenue topics, but not a route/date official fare measure.
- Average fare can legitimately be calculated: no, unless a table explicitly defines revenue and passenger denominators for the same commercial scope. No such DGCA official airfare definition was found for APIx route-window use.
- APIx weighting support: yes, particularly annual city-pair passenger weights.
- 30-day backtest support: not feasible; annual aggregates.
- Limitations: annual granularity; PDF format; not a fare time series.

### 5. Annual Domestic City-Pair Passenger Traffic, Table 5.01

- Official source URL:
  - `https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/dataReports/aviationDataStatistics/airTransport/domestic/yearly/28/Normal/TABLE%205.01%20%28INDIAN%20CITY-WISE%20PASSENGER%20TRAFFIC%29.pdf`
- Dataset/report name: `TABLE 5.01 (INDIAN CITY-WISE PASSENGER TRAFFIC)`.
- Data format: PDF.
- Time coverage: annual selected fiscal-year table in DGCA yearly statistics.
- Update frequency: annual.
- Variables/columns: city 1, city 2, passengers to city 2, passengers from city 2. This exact schema is also visible in public mirrors of the DGCA table, but the official source is the DGCA S3 PDF above.
- Route granularity: city-pair; directional passenger counts are present.
- Airline granularity: no airline field for the domestic city-pair table identified here.
- Actual airfare present: no.
- Passenger/traffic data present: yes.
- Revenue present: no.
- Average fare can legitimately be calculated: no.
- APIx weighting support: yes. This is the strongest official source for APIx route/corridor weights.
- 30-day backtest support: not feasible; annual passenger totals only.
- Limitations: city names rather than necessarily airport-code-normalized keys; annual only; not airline-specific; no fare or booking-window information.

### 6. Official Open Government Data Platform India - DGCA / MoCA-Derived Aviation Datasets

- Official source URL examples:
  - `https://www.data.gov.in/catalog/domestic-traffic-air`
  - `https://www.data.gov.in/resource/airline-wise-city-pair-wise-scheduled-international-passengers-and-freight-carried-indian`
- Data format: catalog/resource pages; some CSV downloads where resources are enabled.
- Time coverage:
  - `Domestic Traffic by air`: published 2014, updated 2014, time-series domestic traffic.
  - `Air Traffic Statistics 2015-16`: annual/month-wise operating and traffic parameters.
  - International city-pair example: annual 2015-16.
- Update frequency: varies; many OGD resources are historical snapshots, not current DGCA live feeds.
- Variables/columns:
  - Domestic traffic catalog: domestic air traffic time series.
  - International city-pair resource: airline, city 1, city 2, passengers to/from city 2, freight.
  - Catalog metadata notes operating parameters such as aircraft utilization, passengers carried, passenger-km, available seat-km, cargo, tonne-km, passenger load factor, and weight load factor.
- Route granularity: available for some city-pair resources, especially international annual city-pair data; domestic route/city-pair data is better sourced from DGCA annual PDFs.
- Airline granularity: available in some OGD resources.
- Actual airfare present: not found.
- Passenger/traffic data present: yes.
- Revenue present: some older OGD catalog metadata mentions financial/revenue-related statistics, but no official route/airline average airfare series was found.
- Average fare can legitimately be calculated: no for APIx unless an official table explicitly defines revenue/passenger as fare. No such table was found.
- APIx weighting support: partial to yes, depending on route/airline granularity.
- 30-day backtest support: not feasible for airfare.
- Limitations: may be historical, incomplete, or not API-enabled; some resources say no API exists.

### 7. DGCA / MoCA Tariff Monitoring and Fare Publication Policy

- Official source URLs:
  - `https://www.pib.gov.in/newsite/erelcontent.aspx?lang=2&reg=48&relid=67355`
  - `https://www.pib.gov.in/newsite/PrintRelease.aspx?lang=2&reg=48&relid=116352`
  - `https://www.pib.gov.in/newsite/PrintRelease.aspx?lang=2&reg=48&relid=86951`
  - `https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=1810467&lang=2&reg=48`
- Data format: official press releases / policy statements.
- Time coverage: 2010, 2012, 2015, 2022 statements about airfare regulation/monitoring.
- Update frequency: policy communications, not a dataset.
- Variables/columns: none as a public data table.
- Route granularity: describes route-wise tariff sheets filed/displayed by airlines.
- Airline granularity: describes scheduled domestic airline compliance obligations.
- Actual airfare present: no public downloadable actual-fare dataset found.
- Passenger/traffic data present: no.
- Revenue present: no.
- Average fare can legitimately be calculated: no.
- APIx weighting support: no direct quantitative weight data.
- 30-day backtest support: no.
- Limitations: confirms DGCA monitoring exists, but does not expose the underlying monitored fare observations as a public dataset.

Key policy findings:

- Air fares are not fixed/regulated under normal conditions; airlines set tariffs under Rule 135.
- Airlines are directed to publish/display route-wise fare sheets/fare buckets.
- DGCA has monitored tariffs on selected routes and checked charges against declared fare ranges.
- This does not establish an official DGCA public average-airfare dataset.

## DGCA Publication Assessment

### A. Average airfare by route

Not found as an official public DGCA downloadable dataset.

DGCA/MoCA materials describe route-wise tariff monitoring and airline route-wise fare sheets, but not a public route-level realized average fare time series.

### B. Average airfare by airline

Not found.

Airline passenger counts, market share, PLF, and operating statistics are available, but no official average-airfare-by-airline public dataset was found.

### C. Average airfare by sector

Not found.

COVID-era fare bands and tariff-monitoring policy references are not equivalent to actual realized sector average fares.

### D. Passenger / traffic / capacity / revenue statistics

Passenger, traffic, capacity, and load-factor data are available.

Revenue is not available in the public domestic monthly/annual route-weight sources inspected in a way that supports airfare calculation. Some older OGD catalog metadata references financial/revenue statistics, but this is not a route/date airfare dataset and should not be used as an airfare proxy without an explicit official definition.

### E. Combination

DGCA provides a strong passenger/traffic/capacity statistical base, but not public official daily airfare data.

## 30 Consecutive Historical Days of Airfare

I did not find an official DGCA source providing at least 30 consecutive historical days of airfare observations.

The available official DGCA materials are monthly or annual aggregates for traffic/operations and policy statements about tariff monitoring. They are not daily fare observations and do not include APIx-style advance-window route quotes.

## Geographic / Route Granularity

Strongest geographic granularity found:

- Annual domestic city-pair passenger traffic.
- Directional passenger counts between city pairs.

Not found:

- Daily route fare observations.
- Route x airline x day x booking-window fare observations.
- Public DGCA average fare by APIx target routes/windows.

## Alignment With APIx Observations

Realistic alignments:

- Use annual city-pair passengers as route/corridor weights.
- Use airline monthly passenger share/market share as airline/source context.
- Use load factor/capacity/ASK trends as explanatory metadata for fare pressure.
- Compare APIx fare-index movements qualitatively against monthly traffic/capacity changes.

Unrealistic alignments:

- Direct validation of APIx fare levels against DGCA official average fares.
- Daily backtesting against DGCA official fare data.
- Booking-window validation using DGCA data.
- Deriving official average fare from revenue/passengers without an explicit DGCA definition.

## Final Classification

DGCA_AIRFARE_DATA: NOT_FOUND

DGCA_WEIGHT_DATA: AVAILABLE

DGCA_30_DAY_BACKTEST: NOT_FEASIBLE

## Exact Limitations

- Official public DGCA data found is mostly PDF and portal-hosted, not analysis-ready CSV.
- Annual city-pair passenger data can weight routes but cannot validate fares.
- Monthly airline traffic reports can weight sources or contextualize market share but cannot validate route fares.
- No public official DGCA daily fare series was found.
- No public official route-airline-day fare series was found.
- No official fare-by-advance-window data was found.
- `revenue / passengers` must not be used as an airfare proxy unless DGCA explicitly defines the fields and scope as average fare; this investigation did not find such a source.

## Sources

- DGCA site map: `https://www.dgca.gov.in/digigov-portal/jsp/dgca/footerLink/sitemap.jsp`
- DGCA portal: `https://www.dgca.gov.in/digigov-portal/`
- DGCA Handbook 2024-25 PDF: `https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/dataReports/aviationDataStatistics/handbookCivilAviation/HANDBOOK%202024-25.pdf`
- DGCA Handbook 2023-24 PDF: `https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/dataReports/aviationDataStatistics/handbookCivilAviation/HANDBOOK%202023-24%20Final%20Draft.pdf`
- DGCA Table 5.01 city-pair passenger traffic PDF: `https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/dataReports/aviationDataStatistics/airTransport/domestic/yearly/28/Normal/TABLE%205.01%20%28INDIAN%20CITY-WISE%20PASSENGER%20TRAFFIC%29.pdf`
- DGCA June 2022 domestic traffic report PDF: `https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/dataReports/aviationDataStatistics/airTransport/domestic/airTraffic/June2022.pdf`
- DGCA December 2023 domestic traffic report PDF: `https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/dataReports/aviationDataStatistics/airTransport/domestic/airTraffic/Traffic%20report%20dec%2023.pdf`
- DGCA monthly airline statistics example: `https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/dataReports/aviationDataStatistics/airTransport/domestic/monthly/indigo22.pdf`
- DGCA monthly airline statistics example: `https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/dataReports/aviationDataStatistics/airTransport/domestic/monthly/india%20one%20air22.pdf`
- Open Government Data Platform, Domestic Traffic by air: `https://www.data.gov.in/catalog/domestic-traffic-air`
- Open Government Data Platform, Air Traffic Statistics 2015-16 international city-pair resource: `https://www.data.gov.in/resource/airline-wise-city-pair-wise-scheduled-international-passengers-and-freight-carried-indian`
- PIB/MoCA, DGCA route-wise tariff monitoring direction, 2010: `https://www.pib.gov.in/newsite/erelcontent.aspx?lang=2&reg=48&relid=67355`
- PIB/MoCA, DGCA Tariff Monitoring Unit, 2015: `https://www.pib.gov.in/newsite/PrintRelease.aspx?lang=2&reg=48&relid=116352`
- PIB/MoCA, IT infrastructure for determining domestic airfares, 2012: `https://www.pib.gov.in/newsite/PrintRelease.aspx?lang=2&reg=48&relid=86951`
- PIB/MoCA, DGCA monitors airfares on selected routes, 2022: `https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=1810467&lang=2&reg=48`
