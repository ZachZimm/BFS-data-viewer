# Census BFS Data Viewer

Interactive viewer for the live Census Business Formation Statistics weekly state applications feed, with locally materialized seasonal adjustment.

## Structure

- `backend/`: FastAPI app that downloads the weekly BFS CSV and date table from Census, materializes raw and STL-adjusted series, and exposes JSON endpoints
- `frontend/`: React + Vite client for filtering, charting, and tabular inspection
- `start.sh`: launches the backend and frontend together for local development

## Data source

The backend loads data directly from:

- `https://www.census.gov/econ/bfs/csv/bfs_state_apps_weekly_nsa.csv`
- `https://www.census.gov/econ/bfs/csv/date_table.csv`

On refresh, the backend stores generated artifacts under `.cache/bfs/current/`, including the downloaded source CSVs, a materialized weekly cache containing both raw (`U`) and locally adjusted (`A`) rows, and cache metadata. Seasonal adjustment is computed once at refresh time with `STL(period=52, robust=True)` and is not recalculated per API call.

## Run locally

### Both servers

```bash
./start.sh
```

This starts FastAPI on `http://127.0.0.1:8000` and the Vite dev server on `http://127.0.0.1:5173`. Stop either with `Ctrl+C`.

### Backend

```bash
./venv/bin/pip install -r requirements.txt
./venv/bin/uvicorn backend.app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server runs on `http://127.0.0.1:5173` and proxies API traffic to the FastAPI server on `http://127.0.0.1:8000`.

## Build for a single-server deployment

```bash
cd frontend
npm run build
cd ..
./venv/bin/uvicorn backend.app.main:app
```

When `frontend/dist/` exists, FastAPI serves the built React app in addition to the `/api/*` routes.
