# Airfare Price Index (APIx) - Prototype

An academic/student research prototype designed to collect, normalize, and calculate a weighted **Airfare Price Index (APIx)** across key domestic and international routes, with scheduled data ingestion, REST API endpoints, and an interactive web dashboard.

---

## Architecture Overview

```
airfare/
├── backend/                  # FastAPI Application
│   ├── app/
│   │   ├── api/              # REST API endpoints (/api/health, etc.)
│   │   ├── core/             # Configuration & structured logging
│   │   ├── db/               # PostgreSQL session & base model
│   │   ├── models/           # SQLAlchemy database entities (Future Phase)
│   │   ├── schemas/          # Pydantic validation models
│   │   ├── services/         # Index calculation & business logic (Future Phase)
│   │   └── main.py           # FastAPI entrypoint
│   ├── tests/                # Pytest test suite
│   ├── requirements.txt      # Python dependencies
│   └── .env.example          # Environment variables template
│
├── scraper/                  # Modular Scraping Engine
│   ├── base/                 # Base scraper class, rate limiters, robots.txt handler
│   ├── airlines/             # Direct airline scrapers (Future Phase)
│   ├── otas/                 # OTA scrapers (Future Phase)
│   ├── scheduler/            # APScheduler collection triggers (Future Phase)
│   └── tests/                # Scraper unit tests
│
├── frontend/                 # React + TypeScript + Vite + Tailwind Dashboard
│   ├── src/
│   │   ├── components/       # UI components (Header, HealthStatus)
│   │   ├── pages/            # View pages (HomePage)
│   │   ├── services/         # Axios API client
│   │   ├── types/            # TypeScript interfaces
│   │   └── App.tsx           # Main application shell
│   ├── package.json          # Node dependencies
│   └── .env.example          # Frontend environment variables template
│
├── data/                     # Data Repository (Separated modes)
│   ├── raw/                  # Raw scraped dumps
│   ├── processed/            # Normalized flight observations
│   ├── reference/            # Official DGCA benchmark reference datasets
│   └── demo/                 # Offline development seed data
│
├── docs/                     # Documentation & architectural specs
├── pytest.ini                # Pytest configuration
├── .gitignore
└── README.md
```

---

## Tech Stack

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy, PostgreSQL, Pydantic v2, Pandas, NumPy, APScheduler
- **Scraping Engine:** Playwright for Python, `urllib.robotparser`
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, Recharts, Lucide Icons
- **Testing:** pytest, pytest-asyncio, HTTPX / FastAPI TestClient

---

## Getting Started Locally

### Prerequisites
- **Python**: 3.12 or newer
- **Node.js**: 18.x or newer (npm 9+)
- **PostgreSQL**: (Optional for Phase 1 health check, required for database persistence in Phase 2)

---

### 1. Backend Setup & Run

1. Open a terminal in the project root:
   ```bash
   python -m venv .venv
   ```

2. Activate the virtual environment:
   - **Windows (PowerShell)**:
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   - **Linux / macOS**:
     ```bash
     source .venv/bin/activate
     ```

3. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```

4. Install Playwright browser drivers (for future scraping phases):
   ```bash
   playwright install chromium
   ```

5. (Optional) Configure environment variables:
   ```bash
   # Copy example if not already created
   cp backend/.env.example backend/.env
   ```

6. Start the FastAPI development server:
   ```bash
   uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
   ```

7. Verify backend health:
   - Health Endpoint: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
   - Interactive Swagger Docs: [http://127.0.0.1:8000/api/docs](http://127.0.0.1:8000/api/docs)

---

### 2. Frontend Setup & Run

1. Open a new terminal in the `frontend` folder:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start Vite dev server:
   ```bash
   npm run dev
   ```

4. Open the web dashboard in your browser:
   - Dashboard: [http://localhost:5173](http://localhost:5173)

---

### 3. Running Automated Tests

Run the complete test suite across backend and scraper modules from the project root:

```bash
pytest
```

To run with verbose output:
```bash
pytest -v
```

---

## Scraping & Data Safety Guidelines

- **No Anti-Bot Bypasses:** The prototype strictly respects website policies, rate limits, and block/CAPTCHA detection without evasive bypass mechanisms.
- **Reference vs Live Separation:** Live scraping pipelines and historical DGCA reference data operate as distinct separated modules.
- **Student Prototype Scope:** Kept minimal and modular without premature microservices or heavy infrastructure.
