from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, time, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .data import METRICS, ensure_cache, get_metadata, get_records, get_series, refresh_data

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
logger = logging.getLogger(__name__)


def _seconds_until_next_midnight() -> float:
    now = datetime.now().astimezone()
    next_day = now.date() + timedelta(days=1)
    next_midnight = datetime.combine(next_day, time.min, tzinfo=now.tzinfo)
    return max((next_midnight - now).total_seconds(), 1.0)


async def _midnight_refresh_loop() -> None:
    while True:
        await asyncio.sleep(_seconds_until_next_midnight())
        try:
            result = refresh_data()
            logger.info(
                "Auto-refreshed Census BFS weekly state applications at midnight: %s rows across %s states",
                result["rowCount"],
                result["stateCount"],
            )
        except Exception:
            logger.exception("Midnight Census BFS weekly data refresh failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await asyncio.to_thread(ensure_cache)
    except Exception:
        logger.exception("Initial weekly Census BFS cache refresh failed")

    refresh_task = asyncio.create_task(_midnight_refresh_loop())
    try:
        yield
    finally:
        refresh_task.cancel()
        try:
            await refresh_task
        except asyncio.CancelledError:
            pass
app = FastAPI(title="Census BFS Weekly State Data Viewer", version="0.4.0", lifespan=lifespan)

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


def _handle_data_error(exc: RuntimeError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/metadata")
def metadata() -> dict:
    try:
        return get_metadata()
    except RuntimeError as exc:
        raise _handle_data_error(exc) from exc


@app.get("/api/series")
def series(
    metric: str = Query(default="BA"),
    entity: str | None = Query(default=None),
    seasonality: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> dict:
    try:
        return get_series(
            metric=_ensure_metric(metric),
            entity=entity,
            seasonality=seasonality,
            start_date=start_date,
            end_date=end_date,
        )
    except RuntimeError as exc:
        raise _handle_data_error(exc) from exc


@app.get("/api/records")
def records(
    entity: str | None = Query(default=None),
    seasonality: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=104, ge=1, le=500),
) -> dict:
    try:
        return get_records(
            entity=entity,
            seasonality=seasonality,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
    except RuntimeError as exc:
        raise _handle_data_error(exc) from exc


@app.post("/api/update-data")
def update_data() -> dict:
    try:
        return refresh_data()
    except RuntimeError as exc:
        raise _handle_data_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Weekly Census BFS refresh failed") from exc


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
