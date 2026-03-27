from __future__ import annotations

import csv
import io
import json
import shutil
import tempfile
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from statistics import fmean
from typing import Any
from urllib.request import Request, urlopen

import pandas as pd
from statsmodels.tsa.seasonal import STL

BASE_DIR = Path(__file__).resolve().parents[2]
CACHE_ROOT = BASE_DIR / ".cache" / "bfs"
CURRENT_DIR = CACHE_ROOT / "current"
RAW_WEEKLY_FILENAME = "raw_weekly_state.csv"
DATE_TABLE_FILENAME = "date_table.csv"
MATERIALIZED_FILENAME = "state_weekly_materialized.csv"
METADATA_FILENAME = "metadata.json"
WEEKLY_URL = "https://www.census.gov/econ/bfs/csv/bfs_state_apps_weekly_nsa.csv"
DATE_TABLE_URL = "https://www.census.gov/econ/bfs/csv/date_table.csv"
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0"}
ADJUSTMENT_METHOD = "STL(period=52, robust=True)"
SEASONALITY_OPTIONS = [
    {"value": "A", "label": "Seasonally adjusted"},
    {"value": "U", "label": "Not seasonally adjusted"},
]
RAW_TO_PUBLIC_METRIC = {
    "BA_NSA": "BA",
    "HBA_NSA": "HBA",
    "WBA_NSA": "WBA",
    "CBA_NSA": "CBA",
}
PUBLIC_TO_RAW_METRIC = {value: key for key, value in RAW_TO_PUBLIC_METRIC.items()}
METRICS: dict[str, dict[str, str]] = {
    "BA": {"label": "Business applications", "format": "integer"},
    "HBA": {"label": "High-propensity business applications", "format": "integer"},
    "WBA": {"label": "Business applications with planned wages", "format": "integer"},
    "CBA": {"label": "Business applications from corporations", "format": "integer"},
}
STATE_NAMES = {
    "AK": "Alaska",
    "AL": "Alabama",
    "AR": "Arkansas",
    "AZ": "Arizona",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DC": "District of Columbia",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "IA": "Iowa",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "MA": "Massachusetts",
    "MD": "Maryland",
    "ME": "Maine",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MO": "Missouri",
    "MS": "Mississippi",
    "MT": "Montana",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "NE": "Nebraska",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NV": "Nevada",
    "NY": "New York",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VA": "Virginia",
    "VT": "Vermont",
    "WA": "Washington",
    "WI": "Wisconsin",
    "WV": "West Virginia",
    "WY": "Wyoming",
}


def _download_text(url: str) -> str:
    request = Request(url, headers=HTTP_HEADERS)
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%m/%d/%Y").date()


def _format_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _parse_number(value: str) -> float | None:
    if value == "":
        return None
    return float(value)


def _load_date_table_from_text(text: str) -> dict[tuple[int, int], tuple[date, date]]:
    table: dict[tuple[int, int], tuple[date, date]] = {}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        table[(int(row["Year"]), int(row["Week"]))] = (
            _parse_date(row["Start date"]),
            _parse_date(row["End date"]),
        )
    return table


def _normalize_raw_rows(raw_text: str, date_table_text: str) -> list[dict[str, Any]]:
    date_table = _load_date_table_from_text(date_table_text)
    rows: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(raw_text))

    for raw in reader:
        state_code = raw["State"]
        if state_code not in STATE_NAMES:
            continue

        year = int(raw["Year"])
        week = int(raw["Week"])
        start_date, end_date = date_table[(year, week)]

        row = {
            "entity_code": state_code,
            "entity_name": STATE_NAMES[state_code],
            "year": year,
            "week": week,
            "start_date": start_date,
            "end_date": end_date,
        }
        for raw_metric, public_metric in RAW_TO_PUBLIC_METRIC.items():
            row[public_metric] = _parse_number(raw[raw_metric])
        rows.append(row)

    rows.sort(key=lambda item: (item["entity_code"], item["start_date"]))
    return rows


def _adjust_state_metric(group: pd.DataFrame, metric: str) -> list[float]:
    series = pd.Series(group[metric].astype(float).to_numpy(), index=pd.to_datetime(group["end_date"]))
    result = STL(series, period=52, robust=True).fit()
    adjusted = series - result.seasonal
    return adjusted.to_list()


def _build_materialized_rows(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frame = pd.DataFrame(raw_rows)
    raw_materialized = frame.copy()
    raw_materialized["seasonality"] = "U"

    adjusted_materialized = frame.copy()
    adjusted_materialized["seasonality"] = "A"

    for state_code, state_frame in frame.groupby("entity_code", sort=True):
        state_frame = state_frame.sort_values("end_date").reset_index(drop=True)
        adjusted_index = adjusted_materialized["entity_code"] == state_code
        for metric in METRICS:
            adjusted_values = _adjust_state_metric(state_frame, metric)
            adjusted_materialized.loc[adjusted_index, metric] = adjusted_values

    combined = pd.concat([raw_materialized, adjusted_materialized], ignore_index=True)
    combined = combined.sort_values(["entity_code", "seasonality", "start_date"]).reset_index(drop=True)

    rows: list[dict[str, Any]] = []
    for row in combined.to_dict(orient="records"):
        rows.append(
            {
                "entity_code": row["entity_code"],
                "entity_name": row["entity_name"],
                "seasonality": row["seasonality"],
                "year": int(row["year"]),
                "week": int(row["week"]),
                "start_date": row["start_date"],
                "end_date": row["end_date"],
                **{metric: float(row[metric]) if row[metric] is not None else None for metric in METRICS},
            }
        )
    return rows


def _write_materialized_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "entity_code",
        "entity_name",
        "seasonality",
        "year",
        "week",
        "start_date",
        "end_date",
        *METRICS.keys(),
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "entity_code": row["entity_code"],
                    "entity_name": row["entity_name"],
                    "seasonality": row["seasonality"],
                    "year": row["year"],
                    "week": row["week"],
                    "start_date": row["start_date"].isoformat(),
                    "end_date": row["end_date"].isoformat(),
                    **{metric: row[metric] for metric in METRICS},
                }
            )


def _build_cache_metadata(rows: list[dict[str, Any]]) -> dict[str, Any]:
    start = min(row["start_date"] for row in rows)
    end = max(row["end_date"] for row in rows)
    return {
        "refreshedAt": datetime.now(timezone.utc).isoformat(),
        "sourceUrls": [WEEKLY_URL, DATE_TABLE_URL],
        "rowCount": len(rows),
        "stateCount": len({row["entity_code"] for row in rows}),
        "dateRange": {
            "start": _format_date(start),
            "end": _format_date(end),
        },
        "adjustmentMethod": ADJUSTMENT_METHOD,
        "cacheVersion": 1,
    }


def _clear_read_caches() -> None:
    get_materialized_rows.cache_clear()
    get_cache_metadata.cache_clear()


def refresh_data() -> dict[str, Any]:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(tempfile.mkdtemp(prefix="stage-", dir=CACHE_ROOT))
    backup_dir: Path | None = None

    try:
        raw_text = _download_text(WEEKLY_URL)
        date_table_text = _download_text(DATE_TABLE_URL)
        raw_rows = _normalize_raw_rows(raw_text, date_table_text)
        materialized_rows = _build_materialized_rows(raw_rows)
        metadata = _build_cache_metadata(materialized_rows)

        (stage_dir / RAW_WEEKLY_FILENAME).write_text(raw_text)
        (stage_dir / DATE_TABLE_FILENAME).write_text(date_table_text)
        _write_materialized_csv(stage_dir / MATERIALIZED_FILENAME, materialized_rows)
        (stage_dir / METADATA_FILENAME).write_text(json.dumps(metadata, indent=2))

        if CURRENT_DIR.exists():
            backup_dir = CACHE_ROOT / f"backup-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            CURRENT_DIR.rename(backup_dir)

        stage_dir.rename(CURRENT_DIR)

        if backup_dir and backup_dir.exists():
            shutil.rmtree(backup_dir)

        _clear_read_caches()
        return {
            "status": "ok",
            "rowCount": metadata["rowCount"],
            "stateCount": metadata["stateCount"],
            "dateRange": metadata["dateRange"],
            "sourceUrls": metadata["sourceUrls"],
            "refreshedAt": metadata["refreshedAt"],
            "adjustmentMethod": metadata["adjustmentMethod"],
        }
    except Exception:
        shutil.rmtree(stage_dir, ignore_errors=True)
        if backup_dir and backup_dir.exists() and not CURRENT_DIR.exists():
            backup_dir.rename(CURRENT_DIR)
        raise


def ensure_cache() -> None:
    if (CURRENT_DIR / MATERIALIZED_FILENAME).exists() and (CURRENT_DIR / METADATA_FILENAME).exists():
        return
    try:
        refresh_data()
    except Exception as exc:
        raise RuntimeError("No weekly BFS cache is available and the initial refresh failed") from exc


@lru_cache(maxsize=1)
def get_cache_metadata() -> dict[str, Any]:
    ensure_cache()
    return json.loads((CURRENT_DIR / METADATA_FILENAME).read_text())


@lru_cache(maxsize=1)
def get_materialized_rows() -> list[dict[str, Any]]:
    ensure_cache()
    rows: list[dict[str, Any]] = []
    with (CURRENT_DIR / MATERIALIZED_FILENAME).open(newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            row = {
                "entity_code": raw["entity_code"],
                "entity_name": raw["entity_name"],
                "seasonality": raw["seasonality"],
                "year": int(raw["year"]),
                "week": int(raw["week"]),
                "start_date": date.fromisoformat(raw["start_date"]),
                "end_date": date.fromisoformat(raw["end_date"]),
            }
            for metric in METRICS:
                row[metric] = _parse_number(raw[metric])
            rows.append(row)
    return rows


def get_metadata() -> dict[str, Any]:
    rows = get_materialized_rows()
    cache_metadata = get_cache_metadata()
    entities = sorted(
        {(row["entity_code"], row["entity_name"]) for row in rows},
        key=lambda item: (item[1], item[0]),
    )
    return {
        "dataset": {
            "id": "state-weekly-applications",
            "label": "State weekly business applications",
            "entityLabel": "State",
            "defaultEntity": "CA",
            "defaultSeasonality": "A",
            "sourceUrls": cache_metadata["sourceUrls"],
            "dateRange": cache_metadata["dateRange"],
            "entities": [{"value": code, "label": name} for code, name in entities],
            "seasonalityOptions": SEASONALITY_OPTIONS,
            "adjustmentMethod": cache_metadata["adjustmentMethod"],
            "lastRefreshedAt": cache_metadata["refreshedAt"],
        },
        "metrics": [
            {"id": key, "label": value["label"], "format": value["format"]}
            for key, value in METRICS.items()
        ],
        "dateRange": cache_metadata["dateRange"],
    }


def get_filtered_rows(
    entity: str | None = None,
    seasonality: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    selected_entity = entity or "CA"
    selected_seasonality = seasonality or "A"
    start = date.fromisoformat(start_date) if start_date else None
    end = date.fromisoformat(end_date) if end_date else None
    filtered: list[dict[str, Any]] = []

    for row in get_materialized_rows():
        if row["entity_code"] != selected_entity:
            continue
        if row["seasonality"] != selected_seasonality:
            continue
        if start and row["end_date"] < start:
            continue
        if end and row["end_date"] > end:
            continue
        filtered.append(row)

    filtered.sort(key=lambda row: row["start_date"])
    return filtered


def get_series(
    metric: str,
    entity: str | None = None,
    seasonality: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    rows = get_filtered_rows(entity, seasonality, start_date, end_date)
    selected_entity = entity or "CA"
    selected_seasonality = seasonality or "A"
    entity_name = rows[0]["entity_name"] if rows else STATE_NAMES.get(selected_entity, selected_entity)

    points = [
        {
            "year": row["year"],
            "week": row["week"],
            "startDate": row["start_date"].isoformat(),
            "endDate": row["end_date"].isoformat(),
            "value": row[metric],
        }
        for row in rows
    ]

    values = [row[metric] for row in rows if row[metric] is not None]
    latest_row = next((row for row in reversed(rows) if row[metric] is not None), None)
    summary = {
        "pointCount": len(values),
        "latestValue": latest_row[metric] if latest_row else None,
        "latestWindow": (
            f"{latest_row['start_date'].isoformat()} to {latest_row['end_date'].isoformat()}"
            if latest_row
            else None
        ),
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "average": fmean(values) if values else None,
    }
    seasonality_label = next(
        option["label"] for option in SEASONALITY_OPTIONS if option["value"] == selected_seasonality
    )

    return {
        "dataset": "state-weekly-applications",
        "datasetLabel": "State weekly business applications",
        "metric": metric,
        "metricLabel": METRICS[metric]["label"],
        "metricFormat": METRICS[metric]["format"],
        "entityCode": selected_entity,
        "entityName": entity_name,
        "seasonality": selected_seasonality,
        "seasonalityLabel": seasonality_label,
        "points": points,
        "summary": summary,
    }


def get_records(
    entity: str | None = None,
    seasonality: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 104,
) -> dict[str, Any]:
    rows = get_filtered_rows(entity, seasonality, start_date, end_date)
    selected_entity = entity or "CA"
    selected_seasonality = seasonality or "A"
    trimmed = sorted(rows, key=lambda row: row["start_date"], reverse=True)[:limit]
    payload_rows = []

    for row in trimmed:
        item = {
            "year": row["year"],
            "week": row["week"],
            "entityCode": row["entity_code"],
            "entityName": row["entity_name"],
            "seasonality": row["seasonality"],
            "startDate": row["start_date"].isoformat(),
            "endDate": row["end_date"].isoformat(),
        }
        for metric in METRICS:
            item[metric] = row[metric]
        payload_rows.append(item)

    return {
        "dataset": "state-weekly-applications",
        "datasetLabel": "State weekly business applications",
        "entityCode": selected_entity,
        "seasonality": selected_seasonality,
        "rows": payload_rows,
    }
