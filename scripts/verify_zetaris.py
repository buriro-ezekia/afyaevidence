#!/usr/bin/env python3
"""Read one synthetic registry table through the supplied Zetaris JDBC driver."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date, datetime
import getpass
import importlib
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable, MutableMapping, Sequence


DRIVER_CLASS = "com.zetaris.lightning.jdbc.LightningDriver"
DRIVER_FILENAME = "ndp-jdbc-driver-2.4.3.1-7eff043-driver.jar"
DEFAULT_URL = "jdbc:zetaris:lightning@localhost:10000"
DATASET_ID = "fx_probe_v1"
COLUMNS = (
    "dataset_id", "facility_id", "district_id", "facility_type", "active_from", "active_to"
)
DEFAULT_FIXTURE = Path(__file__).resolve().parents[1] / "data/synthetic/probe/facility_registry.csv"
EXPECTED_ROWS = tuple(
    (DATASET_ID, f"F{i:03d}", "D001", "health_centre" if i <= 2 else "dispensary", "2024-01-01", None)
    for i in range(1, 7)
)
TABLE_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\Z")
URL_PATTERN = re.compile(r"jdbc:zetaris:lightning@(?:[A-Za-z0-9_.-]+|\[[0-9A-Fa-f:]+\]):([0-9]{1,5})\Z")


class Blocked(RuntimeError):
    """A prerequisite is absent; no live PASS is possible."""


class VerificationFailure(RuntimeError):
    """Observed or expected rows do not satisfy the probe contract."""


def load_env_file(path: Path, environ: MutableMapping[str, str]) -> None:
    """Load literal KEY=value settings without executing or expanding their contents."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        raise Blocked("Cannot read the requested local environment file.") from None
    settings: dict[str, str] = {}
    for number, original in enumerate(lines, 1):
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise Blocked(f"Malformed environment setting on line {number}.")
        if value[:1] in ("'", '"'):
            if len(value) < 2 or value[-1] != value[0]:
                raise Blocked(f"Unclosed quoted environment value on line {number}.")
            value = value[1:-1]
        settings[key] = value
    for key, value in settings.items():
        environ.setdefault(key, value)


def build_query(table: str) -> str:
    if not TABLE_PATTERN.fullmatch(table):
        raise Blocked("Set a two-part table identifier such as AFYAEVIDENCE.facility_registry; only letters, digits and underscores are allowed.")
    return f"SELECT {', '.join(COLUMNS)} FROM {table} WHERE dataset_id = '{DATASET_ID}' LIMIT 7"


def normalise_row(row: Sequence[Any]) -> tuple[str | None, ...]:
    if len(row) != len(COLUMNS):
        raise VerificationFailure("A registry row has an unexpected number of columns.")
    result: list[str | None] = []
    for column, value in zip(COLUMNS, row):
        if column == "active_to" and (value is None or value == ""):
            result.append(None)
            continue
        if value is None:
            raise VerificationFailure("A required registry value is missing.")
        if isinstance(value, datetime):
            raise VerificationFailure("A registry date unexpectedly contains a timestamp.")
        text_value = value.isoformat() if isinstance(value, date) else str(value)
        if not text_value or text_value != text_value.strip():
            raise VerificationFailure("A registry value is empty or contains surrounding whitespace.")
        if column in ("active_from", "active_to"):
            try:
                parsed = date.fromisoformat(text_value)
            except ValueError:
                raise VerificationFailure("A registry date is not an ISO calendar date.") from None
            if parsed.isoformat() != text_value:
                raise VerificationFailure("A registry date is not in YYYY-MM-DD form.")
        result.append(text_value)
    if result[5] is not None and str(result[5]) <= str(result[4]):
        raise VerificationFailure("A registry active period is empty or reversed.")
    return tuple(result)


def read_fixture(path: Path) -> list[tuple[str | None, ...]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            if tuple(next(reader, ())) != COLUMNS:
                raise VerificationFailure("The fixture header differs from the registry contract.")
            rows = [normalise_row(row) for row in reader]
    except (OSError, UnicodeError, csv.Error):
        raise Blocked("Cannot read the synthetic registry fixture.") from None
    if len(rows) != 6:
        raise VerificationFailure("The probe fixture must contain exactly six facilities.")
    if {row[1] for row in rows} != {f"F{i:03d}" for i in range(1, 7)}:
        raise VerificationFailure("The probe fixture must contain each of F001 to F006 exactly once.")
    if any(row[0] != DATASET_ID or row[2] != "D001" for row in rows):
        raise VerificationFailure("The probe fixture dataset or district differs from its contract.")
    if Counter(rows) != Counter(EXPECTED_ROWS):
        raise VerificationFailure("The probe fixture types or active dates differ from the fixed synthetic contract.")
    return rows


def reconcile_rows(expected: Sequence[Sequence[Any]], observed: Sequence[Sequence[Any]]) -> None:
    wanted = Counter(normalise_row(row) for row in expected)
    actual = Counter(normalise_row(row) for row in observed)
    if wanted != actual:
        raise VerificationFailure("Project-table rows differ from the six-row fixture (missing, extra, duplicate or changed values).")


def check_live(connect: Callable[..., Any], jar: Path, url: str, username: str,
               password: str, query: str, expected: Sequence[Sequence[Any]],
               discover: bool = False) -> None:
    connection = cursor = None
    try:
        connection = connect(DRIVER_CLASS, url, [username, password], str(jar))
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
        if row is None or len(row) != 1 or str(row[0]) != "1":
            raise VerificationFailure("SELECT 1 did not return one integer-like value of 1.")
        print("ZETARIS_CONNECTION=PASS", flush=True)
        if discover:
            for label, statement in (("LIGHTNING_DATABASES", "SHOW LIGHTNING DATABASES"),
                                     ("DATASOURCES", "SHOW DATASOURCES")):
                cursor.execute(statement)
                records = cursor.fetchmany(31)
                print(f"{label}_ROWS={min(len(records), 30)}", flush=True)
                print(f"{label}_TRUNCATED={'YES' if len(records) > 30 else 'NO'}", flush=True)
                # SHOW responses can contain connection properties. Never dump raw rows.
                description = getattr(cursor, "description", None) or []
                name_columns = {
                    "name", "database", "database_name", "datasource", "datasource_name",
                    "lightning_database_name", "source", "source_name"
                }
                indexes = [i for i, item in enumerate(description)
                           if str(item[0]).lower().replace(" ", "_") in name_columns]
                for record in records[:30]:
                    for index in indexes:
                        if index < len(record) and record[index] is not None:
                            name = str(record[index])
                            if re.fullmatch(r"[A-Za-z0-9_. -]{1,100}", name):
                                print(f"{label}_NAME={name}", flush=True)
            print("ZETARIS_DISCOVERY=PASS", flush=True)
            print("ZETARIS_PROJECT_TABLE=NOT_RUN", flush=True)
            return
        cursor.execute(query)
        # Seven rows expose overflow while remaining bounded; six exact rows are required.
        observed = cursor.fetchmany(7)
        reconcile_rows(expected, observed)
        print("ZETARIS_PROJECT_TABLE=PASS", flush=True)
        print(f"ZETARIS_PROJECT_ROWS={len(observed)}", flush=True)
    except VerificationFailure:
        raise
    except Exception:
        raise Blocked("JDBC connection or read is unavailable. Check the local service, Java, login, table registration and permissions; raw driver errors are withheld to protect credentials.") from None
    finally:
        for resource in (cursor, connection):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    # Never print raw driver exceptions, which may contain credentials.
                    pass


def validate_jar(raw_path: str) -> Path:
    if not raw_path:
        raise Blocked("Set ZETARIS_JDBC_JAR or --jar to the supplied driver's absolute path.")
    jar = Path(raw_path)
    if not jar.is_absolute() or not jar.is_file() or jar.name != DRIVER_FILENAME:
        raise Blocked(f"The JAR must be an existing absolute path ending in {DRIVER_FILENAME}.")
    return jar


def validate_url(url: str) -> str:
    match = URL_PATTERN.fullmatch(url)
    if match is None or not 1 <= int(match.group(1)) <= 65535:
        raise Blocked("Use a supplied Zetaris JDBC URL in jdbc:zetaris:lightning@host:port form.")
    return url


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-fixture", action="store_true", help="Check local fixture only; does not connect to Zetaris.")
    mode.add_argument("--discover", action="store_true", help="Read-only connection and object discovery; does not verify project data.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--env-file", type=Path, help="Explicit local literal KEY=value file; existing environment wins.")
    parser.add_argument("--table", help="Existing two-part registered Zetaris table, or ZETARIS_PROBE_TABLE.")
    parser.add_argument("--jar", help="Absolute supplied JAR path, or ZETARIS_JDBC_JAR.")
    parser.add_argument("--url", help="Supplied Zetaris JDBC URL, or ZETARIS_JDBC_URL.")
    args = parser.parse_args(argv)
    result_tag = "FIXTURE" if args.check_fixture else ("ZETARIS_DISCOVERY" if args.discover else "ZETARIS_PROJECT_TABLE")
    try:
        if args.env_file:
            load_env_file(args.env_file, os.environ)
        expected = [] if args.discover else read_fixture(args.fixture)
        if args.check_fixture:
            print("FIXTURE=PASS")
            print(f"FIXTURE_ROWS={len(expected)}")
            print("ZETARIS_CONNECTION=NOT_RUN")
            print("ZETARIS_PROJECT_TABLE=NOT_RUN")
            return 0
        table = args.table or os.environ.get("ZETARIS_PROBE_TABLE", "")
        query = "" if args.discover else build_query(table)
        jar = validate_jar(args.jar or os.environ.get("ZETARIS_JDBC_JAR", ""))
        url = validate_url(args.url or os.environ.get("ZETARIS_JDBC_URL") or DEFAULT_URL)
        try:
            jaydebeapi = importlib.import_module("jaydebeapi")
        except ImportError:
            raise Blocked("JayDeBeApi/JPype is unavailable in this Python environment; use the previously verified JDBC environment.") from None
        username = os.environ.get("ZETARIS_USERNAME", "")
        password = os.environ.get("ZETARIS_PASSWORD", "")
        if not username.strip():
            if not sys.stdin.isatty():
                raise Blocked("Set ZETARIS_USERNAME locally or run interactively for a user-ID prompt.")
            username = input("Zetaris JDBC user ID: ")
        if not password.strip():
            if not sys.stdin.isatty():
                raise Blocked("Set ZETARIS_PASSWORD locally or run interactively for a hidden password prompt.")
            password = getpass.getpass("Zetaris JDBC password: ")
        if not username.strip() or not password.strip():
            raise Blocked("A non-empty Zetaris user ID and password are required.")
        check_live(jaydebeapi.connect, jar, url, username, password, query, expected, discover=args.discover)
        return 0
    except Blocked as exc:
        print(f"{result_tag}=BLOCKED\n{exc}", file=sys.stderr)
        return 2
    except VerificationFailure as exc:
        print(f"{result_tag}=FAIL\n{exc}", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print(f"{result_tag}=BLOCKED\nVerification cancelled before completion.", file=sys.stderr)
        return 2
    except Exception:
        print(f"{result_tag}=FAIL\nJDBC execution failed. Check local service, Java, login, table registration and permissions. Raw driver errors are withheld to protect credentials.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
