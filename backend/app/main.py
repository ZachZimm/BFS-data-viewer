from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from .data import METRICS, build_download_csv, get_metadata, get_records, get_series

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

app = FastAPI(title="Census BFS State Data Viewer", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _ensure_metric(metric: str) -> str:
    if metric not in METRICS:
        raise HTTPException(status_code=404, detail=f"Unknown metric: {metric}")
    return metric


def _csv_response(content: str, filename: str) -> StreamingResponse:
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/metadata")
def metadata() -> dict:
    return get_metadata()


@app.get("/api/series")
def series(
    metric: str = Query(default="BA_NSA"),
    entity: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> dict:
    return get_series(
        metric=_ensure_metric(metric),
        entity=entity,
        start_date=start_date,
        end_date=end_date,
    )


@app.get("/api/records")
def records(
    entity: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=104, ge=1, le=500),
) -> dict:
    return get_records(
        entity=entity,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@app.get("/api/download")
def download(
    entity: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> StreamingResponse:
    entity_part = (entity or "CA").lower()
    filename = f"bfs-state-{entity_part}-{(start_date or 'all')}-{(end_date or 'all')}.csv"
    return _csv_response(build_download_csv(entity, start_date, end_date), filename)


if FRONTEND_DIST.exists():

    @app.get("/", include_in_schema=False)
    def frontend_index() -> FileResponse:
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend_assets(path: str) -> FileResponse:
        candidate = FRONTEND_DIST / path
        if path and candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
