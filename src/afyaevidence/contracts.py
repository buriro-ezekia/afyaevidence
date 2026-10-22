"""Strict CSV normalisation and order-independent, duplicate-preserving hashes."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import date, datetime

SCHEMAS = {
    "facility_registry": (
        ("dataset_id", "id"), ("facility_id", "id"), ("district_id", "id"),
        ("facility_type", "id"), ("active_from", "date"), ("active_to", "date?"),
    ),
    "malaria_monthly": (
        ("dataset_id", "id"), ("report_id", "id"), ("report_version", "version"),
        ("facility_id", "id"), ("period_month", "month"),
        ("suspected_episodes", "count?"), ("tested_episodes", "count?"),
        ("positive_episodes", "count?"),
    ),
    "reporting_log": (
        ("dataset_id", "id"), ("report_id", "id"), ("report_version", "version"),
        ("received_at_utc", "timestamp"), ("status", "status"),
        ("declared_complete", "bool"),
    ),
}
ALGORITHM = "afya-canonical-rows-v1"


def normalise(value, kind):
    if value is None or value == "":
        if kind.endswith("?"):
            return None
        raise ValueError(f"Missing required {kind}")
    if kind in {"version", "count?"}:
        if isinstance(value, bool) or not re.fullmatch(r"0|[1-9][0-9]*", str(value)):
            raise ValueError("Expected non-negative decimal integer")
        number = int(value)
        if kind == "version" and number < 1:
            raise ValueError("Report version must be positive")
        return number
    if kind == "bool":
        if value is True or value == "true":
            return True
        if value is False or value == "false":
            return False
        raise ValueError("Expected true or false")
    if kind in {"date", "date?", "month"}:
        if isinstance(value, datetime):
            raise ValueError("Datetime cannot substitute for date")
        text = value.isoformat() if isinstance(value, date) else str(value)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            raise ValueError("Expected ISO date")
        parsed = date.fromisoformat(text)
        if kind == "month" and parsed.day != 1:
            raise ValueError("Month must start on day 1")
        return text
    if kind == "timestamp":
        if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value
        ):
            raise ValueError("Expected whole-second UTC timestamp")
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        return value
    if kind == "status" and value not in {"accepted", "withdrawn"}:
        raise ValueError("Unknown status")
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("Expected exact non-empty string")
    return value


def normalise_rows(table, rows):
    schema = SCHEMAS[table]
    fields = {name for name, _ in schema}
    result = []
    for row in rows:
        if set(row) != fields:
            raise ValueError(f"Unexpected fields in {table}")
        result.append({name: normalise(row[name], kind) for name, kind in schema})
    return result


def csv_bytes(table, rows):
    rows = normalise_rows(table, rows)
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    fields = [name for name, _ in SCHEMAS[table]]
    writer.writerow(fields)
    for row in rows:
        writer.writerow([
            "" if row[name] is None else
            str(row[name]).lower() if isinstance(row[name], bool) else row[name]
            for name in fields
        ])
    return output.getvalue().encode("utf-8")


def read_csv(table, content):
    reader = csv.DictReader(io.StringIO(content.decode("utf-8"), newline=""))
    if reader.fieldnames != [name for name, _ in SCHEMAS[table]]:
        raise ValueError(f"Incorrect CSV header for {table}")
    return normalise_rows(table, list(reader))


def canonical_digest(table, rows):
    fields = [name for name, _ in SCHEMAS[table]]
    encoded = sorted(
        json.dumps([row[name] for name in fields], ensure_ascii=False,
                   separators=(",", ":"), allow_nan=False).encode("utf-8")
        for row in normalise_rows(table, rows)
    )
    return hashlib.sha256(b"".join(row + b"\n" for row in encoded)).hexdigest()
