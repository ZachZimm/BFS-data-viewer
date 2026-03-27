from __future__ import annotations

import csv
import io
from datetime import date, datetime
from functools import lru_cache
from statistics import fmean
from typing import Any
from urllib.request import Request, urlopen

MONTHLY_URL = "https://www.census.gov/econ/bfs/csv/bfs_monthly.csv"
MONTH_DATE_TABLE_URL = "https://www.census.gov/econ/bfs/csv/month_date_table.csv"
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0"}
MONTH_COLUMNS = [
    ("jan", 1),
    ("feb", 2),
    ("mar", 3),
    ("apr", 4),
    ("may", 5),
    ("jun", 6),
    ("jul", 7),
    ("aug", 8),
    ("sep", 9),
    ("oct", 10),
    ("nov", 11),
    ("dec", 12),
]
SERIES_TO_METRIC = {
    "BA_BA": "BA",
    "BA_HBA": "HBA",
    "BA_WBA": "WBA",
    "BA_CBA": "CBA",
}
METRICS: dict[str, dict[str, str]] = {
    "BA": {"label": "Business applications", "format": "integer"},
    "HBA": {"label": "High-propensity business applications", "format": "integer"},
    "WBA": {"label": "Business applications with planned wages", "format": "integer"},
    "CBA": {"label": "Business applications from corporations", "format": "integer"},
}
SEASONALITY_OPTIONS = [
    {"value": "A", "label": "Seasonally adjusted"},
    {"value": "U", "label": "Not seasonally adjusted"},
]
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
    "PR": "Puerto Rico",
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


@lru_cache(maxsize=1)
def _load_month_date_table() -> dict[tuple[int, int], tuple[date, date]]:
    table: dict[tuple[int, int], tuple[date, date]] = {}
    reader = csv.DictReader(io.StringIO(_download_text(MONTH_DATE_TABLE_URL)))
    for row in reader:
        key = (int(row["Year"]), int(row["Month"]))
        table[key] = (_parse_date(row["Start date"]), _parse_date(row["End date"]))
    return table


@lru_cache(maxsize=1)
def get_monthly_rows() -> list[dict[str, Any]]:
    date_table = _load_month_date_table()
    rows_by_key: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    reader = csv.DictReader(io.StringIO(_download_text(MONTHLY_URL)))

    for raw in reader:
        if raw["naics_sector"] != "TOTAL":
            continue
        if raw["series"] not in SERIES_TO_METRIC:
            continue
        if raw["geo"] not in STATE_NAMES:
            continue

        metric = SERIES_TO_METRIC[raw["series"]]
        geo = raw["geo"]
        seasonal_adjustment = raw["sa"]
        year = int(raw["year"])

        for month_name, month_number in MONTH_COLUMNS:
            value = _parse_number(raw[month_name])
            if value is None:
                continue

            start_date, end_date = date_table[(year, month_number)]
            key = (geo, seasonal_adjustment, year, month_number)
            if key not in rows_by_key:
                rows_by_key[key] = {
                    "entity_code": geo,
                    "entity_name": STATE_NAMES[geo],
                    "seasonal_adjustment": seasonal_adjustment,
                    "year": year,
                    "month": month_number,
                    "start_date": start_date,
                    "end_date": end_date,
                    **{metric_name: None for metric_name in METRICS},
                }

            rows_by_key[key][metric] = value

    rows = list(rows_by_key.values())
    rows.sort(key=lambda item: (item["entity_code"], item["seasonal_adjustment"], item["start_date"]))
    return rows


def refresh_data() -> dict[str, Any]:
    _load_month_date_table.cache_clear()
    get_monthly_rows.cache_clear()
    metadata = get_metadata()
    rows = get_monthly_rows()
    return {
        "status": "ok",
        "rowCount": len(rows),
        "stateCount": len(metadata["dataset"]["entities"]),
        "dateRange": metadata["dateRange"],
        "sourceUrls": metadata["dataset"]["sourceUrls"],
    }


def get_metadata() -> dict[str, Any]:
    rows = get_monthly_rows()
    entities = sorted(
        {(row["entity_code"], row["entity_name"]) for row in rows},
        key=lambda item: (item[1], item[0]),
    )
    start = min(row["start_date"] for row in rows)
    end = max(row["end_date"] for row in rows)

    return {
        "dataset": {
            "id": "state-monthly-applications",
            "label": "State monthly business applications",
            "entityLabel": "State",
            "defaultEntity": "CA",
            "defaultSeasonality": "A",
            "sourceUrls": [MONTHLY_URL, MONTH_DATE_TABLE_URL],
            "dateRange": {
                "start": _format_date(start),
                "end": _format_date(end),
            },
            "entities": [{"value": code, "label": name} for code, name in entities],
            "seasonalityOptions": SEASONALITY_OPTIONS,
        },
        "metrics": [
            {"id": key, "label": value["label"], "format": value["format"]}
            for key, value in METRICS.items()
        ],
        "dateRange": {
            "start": _format_date(start),
            "end": _format_date(end),
        },
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
    start_key = (start.year, start.month) if start else None
    end_key = (end.year, end.month) if end else None
    filtered: list[dict[str, Any]] = []

    for row in get_monthly_rows():
        if row["entity_code"] != selected_entity:
            continue
        if row["seasonal_adjustment"] != selected_seasonality:
            continue
        row_key = (row["year"], row["month"])
        if start_key and row_key < start_key:
            continue
        if end_key and row_key > end_key:
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
            "month": row["month"],
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
        "dataset": "state-monthly-applications",
        "datasetLabel": "State monthly business applications",
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
            "month": row["month"],
            "entityCode": row["entity_code"],
            "entityName": row["entity_name"],
            "seasonality": row["seasonal_adjustment"],
            "startDate": row["start_date"].isoformat(),
            "endDate": row["end_date"].isoformat(),
        }
        for metric in METRICS:
            item[metric] = row[metric]
        payload_rows.append(item)

    return {
        "dataset": "state-monthly-applications",
        "datasetLabel": "State monthly business applications",
        "entityCode": selected_entity,
        "seasonality": selected_seasonality,
        "rows": payload_rows,
    }
