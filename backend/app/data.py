from __future__ import annotations

import csv
import io
from datetime import date, datetime
from functools import lru_cache
from statistics import fmean
from typing import Any
from urllib.request import Request, urlopen

STATE_WEEKLY_URL = "https://www.census.gov/econ/bfs/csv/bfs_state_apps_weekly_nsa.csv"
DATE_TABLE_URL = "https://www.census.gov/econ/bfs/csv/date_table.csv"
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0"}

METRICS: dict[str, dict[str, str]] = {
    "BA_NSA": {"label": "Business applications", "format": "integer"},
    "HBA_NSA": {"label": "High-propensity applications", "format": "integer"},
    "WBA_NSA": {"label": "Applications with wages", "format": "integer"},
    "CBA_NSA": {"label": "Corporate applications", "format": "integer"},
    "YY_BA_NSA": {"label": "Business applications YoY", "format": "percent"},
    "YY_HBA_NSA": {"label": "High-propensity YoY", "format": "percent"},
    "YY_WBA_NSA": {"label": "Applications with wages YoY", "format": "percent"},
    "YY_CBA_NSA": {"label": "Corporate applications YoY", "format": "percent"},
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


@lru_cache(maxsize=1)
def _load_date_table() -> dict[tuple[int, int], tuple[date, date]]:
    table: dict[tuple[int, int], tuple[date, date]] = {}
    reader = csv.DictReader(io.StringIO(_download_text(DATE_TABLE_URL)))
    for row in reader:
        key = (int(row["Year"]), int(row["Week"]))
        table[key] = (_parse_date(row["Start date"]), _parse_date(row["End date"]))
    return table


@lru_cache(maxsize=1)
def get_state_rows() -> list[dict[str, Any]]:
    date_table = _load_date_table()
    rows: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(_download_text(STATE_WEEKLY_URL)))

    for raw in reader:
        year = int(raw["Year"])
        week = int(raw["Week"])
        start_date, end_date = date_table[(year, week)]
        state_code = raw["State"]

        row: dict[str, Any] = {
            "Year": year,
            "Week": week,
            "entity_code": state_code,
            "entity_name": STATE_NAMES.get(state_code, state_code),
            "start_date": start_date,
            "end_date": end_date,
        }
        for metric in METRICS:
            row[metric] = _parse_number(raw[metric])
        rows.append(row)

    rows.sort(key=lambda item: (item["entity_code"], item["start_date"]))
    return rows


def get_metadata() -> dict[str, Any]:
    rows = get_state_rows()
    states = sorted(
        {(row["entity_code"], row["entity_name"]) for row in rows},
        key=lambda item: (item[1], item[0]),
    )
    start = min(row["start_date"] for row in rows)
    end = max(row["end_date"] for row in rows)

    return {
        "dataset": {
            "id": "state",
            "label": "State weekly applications",
            "entityLabel": "State",
            "defaultEntity": "CA",
            "sourceUrls": [STATE_WEEKLY_URL, DATE_TABLE_URL],
            "dateRange": {
                "start": _format_date(start),
                "end": _format_date(end),
            },
            "entities": [{"value": code, "label": name} for code, name in states],
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
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    selected_entity = entity or "CA"
    start = date.fromisoformat(start_date) if start_date else None
    end = date.fromisoformat(end_date) if end_date else None
    filtered: list[dict[str, Any]] = []

    for row in get_state_rows():
        if row["entity_code"] != selected_entity:
            continue
        if start and row["start_date"] < start:
            continue
        if end and row["end_date"] > end:
            continue
        filtered.append(row)

    filtered.sort(key=lambda row: row["start_date"])
    return filtered


def get_series(
    metric: str,
    entity: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    rows = get_filtered_rows(entity, start_date, end_date)
    selected_entity = entity or "CA"
    entity_name = rows[0]["entity_name"] if rows else STATE_NAMES.get(selected_entity, selected_entity)

    points = [
        {
            "year": row["Year"],
            "week": row["Week"],
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

    return {
        "dataset": "state",
        "datasetLabel": "State weekly applications",
        "metric": metric,
        "metricLabel": METRICS[metric]["label"],
        "metricFormat": METRICS[metric]["format"],
        "entityCode": selected_entity,
        "entityName": entity_name,
        "points": points,
        "summary": summary,
    }


def get_records(
    entity: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 104,
) -> dict[str, Any]:
    rows = get_filtered_rows(entity, start_date, end_date)
    selected_entity = entity or "CA"
    trimmed = sorted(rows, key=lambda row: row["start_date"], reverse=True)[:limit]
    payload_rows = []

    for row in trimmed:
        item = {
            "year": row["Year"],
            "week": row["Week"],
            "entityCode": row["entity_code"],
            "entityName": row["entity_name"],
            "startDate": row["start_date"].isoformat(),
            "endDate": row["end_date"].isoformat(),
        }
        for metric in METRICS:
            item[metric] = row[metric]
        payload_rows.append(item)

    return {
        "dataset": "state",
        "datasetLabel": "State weekly applications",
        "entityCode": selected_entity,
        "rows": payload_rows,
    }


def build_download_csv(
    entity: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    rows = get_filtered_rows(entity, start_date, end_date)
    fieldnames = [
        "year",
        "week",
        "entityCode",
        "entityName",
        "startDate",
        "endDate",
        *METRICS.keys(),
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for row in rows:
        writer.writerow(
            {
                "year": row["Year"],
                "week": row["Week"],
                "entityCode": row["entity_code"],
                "entityName": row["entity_name"],
                "startDate": row["start_date"].isoformat(),
                "endDate": row["end_date"].isoformat(),
                **{metric: row[metric] for metric in METRICS},
            }
        )

    return output.getvalue()
