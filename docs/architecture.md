# Airfare Price Index (APIx) - Architecture Overview

## 1. Project Mission & Context
The **Airfare Price Index (APIx)** is a student/research prototype designed to track, aggregate, and measure passenger airfare movements across key domestic and international flight corridors.

The system is structured as a modular monorepo to ensure clean separation of concerns between data collection (scraping), data storage/normalization, index calculation, and presentation (REST API & Web Dashboard).

```
+-------------------------------------------------------------+
|                       Web Dashboard                         |
|             (React + TypeScript + Vite + Tailwind)          |
+------------------------------+------------------------------+
                               | REST API
+------------------------------v------------------------------+
|                      FastAPI Backend                        |
|  - Health & Metrics API                                     |
|  - Index Engine (Daily/Weekly/Monthly) [Future Phase]       |
|  - Data Normalization Pipeline [Future Phase]               |
+------------------------------+------------------------------+
                               | SQLAlchemy ORM
+------------------------------v------------------------------+
|                    PostgreSQL Database                      |
|  - Raw Quotes, Normalized Observations, Reference Indices    |
+------------------------------^------------------------------+
                               |
+------------------------------+------------------------------+
|                   Modular Scraper Engine                    |
|  - Rate-Limited Playwright Runners                          |
|  - Robots.txt & Policy Awareness                            |
|  - CAPTCHA/Block Graceful Handling                          |
|  - Scheduled Jobs (APScheduler)                             |
+-------------------------------------------------------------+
```

## 2. Core Modules

1. **`backend/`**:
   - **`app/api/`**: REST endpoints (e.g. `/api/health`, `/api/index`, `/api/quotes`).
   - **`app/core/`**: Configuration management via Pydantic Settings, environment loading, structured logging.
   - **`app/db/`**: PostgreSQL connection pooling and SQLAlchemy Base declaration.
   - **`app/models/`**: ORM models for airfare quotes, routes, and computed indices.
   - **`app/schemas/`**: Pydantic validation schemas for API inputs and outputs.
   - **`app/services/`**: Index calculation algorithms and data aggregation pipelines.

2. **`scraper/`**:
   - **`base/`**: Base scraper class, rate limiters, robots.txt validator, and block event handlers.
   - **`airlines/`**: Direct airline portal scraper implementations (e.g., Indigo, Air India, SpiceJet).
   - **`otas/`**: Online Travel Agency scraper implementations (e.g., MakeMyTrip, EaseMyTrip).
   - **`scheduler/`**: APScheduler triggers for periodic data collection.

3. **`frontend/`**:
   - React 18 / 19 + TypeScript + Vite.
   - Tailwind CSS for responsive styling.
   - Recharts for time-series index visualization.
   - Lucide React for UI iconography.

4. **`data/`**:
   - **`raw/`**: Scraped raw payloads.
   - **`processed/`**: Cleaned and validated dataset dumps.
   - **`reference/`**: Official DGCA reference benchmarks.
   - **`demo/`**: Mock/synthetic dataset for offline testing and development.

## 3. Scraping Ethics & Guidelines
- Strictly adherence to rate limits (minimum default 3-second delay between requests).
- Respect `robots.txt` disallow directives.
- Honest identifying User-Agent headers.
- Graceful degradation on block/challenge encounters without circumvention attempts.
- Clear separation between live scraping mode and demo/reference mode.
