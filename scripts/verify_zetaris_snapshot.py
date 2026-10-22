#!/usr/bin/env python3
"""Reconcile a complete synthetic snapshot through the exact Zetaris JDBC driver.

Operator verification only: SELECT statements, no provisioning, Spark or fallback.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import getpass
import hashlib
import importlib
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from afyaevidence.contracts import SCHEMAS, canonical_digest, normalise
from evals.reference import analyse, load_snapshot
from scripts.verify_zetaris import (Blocked, DEFAULT_URL, DRIVER_CLASS,
                                    VerificationFailure, load_env_file, validate_jar, validate_url)

DEFAULT_DATASET = "fx_32e8b610"
DEFAULT_DATABASE = "AFYAEVIDENCE_REVISION"
DEFAULT_CUTOFF = "2026-01-15T00:00:00Z"
ROW_CAP = 2000


def validate_scope(database, dataset_id):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database):
        raise Blocked("Database must be a single identifier containing letters, digits and underscores.")
    if not re.fullmatch(r"fx_[0-9a-f]{8}", dataset_id):
        raise Blocked("Dataset must be an opaque fx_ identifier from the synthetic suite.")


def source_queries(database, dataset_id):
    validate_scope(database, dataset_id)
    # No dataset filter: the registered tables must contain exactly this snapshot.
    return {table: f"SELECT {', '.join(f for f, _ in schema)} FROM {database}.{table} LIMIT {ROW_CAP + 1}"
            for table, schema in SCHEMAS.items()}


def join_query(database, dataset_id):
    validate_scope(database, dataset_id)
    return (
        "SELECT m.dataset_id, m.report_id, m.report_version, m.facility_id, "
        "m.period_month, m.suspected_episodes, m.tested_episodes, m.positive_episodes, "
        "f.district_id, l.received_at_utc, l.status, l.declared_complete "
        f"FROM {database}.malaria_monthly m "
        f"JOIN {database}.reporting_log l ON m.dataset_id = l.dataset_id "
        "AND m.report_id = l.report_id AND m.report_version = l.report_version "
        f"JOIN {database}.facility_registry f ON m.dataset_id = f.dataset_id "
        f"AND m.facility_id = f.facility_id LIMIT {ROW_CAP + 1}"
    )


def read_bounded(cursor, query):
    cursor.execute(query)
    rows = []
    while len(rows) <= ROW_CAP:
        batch = cursor.fetchmany(min(256, ROW_CAP + 1 - len(rows)))
        if not batch:
            return rows
        rows.extend(batch)
    raise VerificationFailure("Source read exceeded the 2,000-row defensive cap; no truncated PASS.")


def adapt_value(value, kind):
    # JayDeBeApi may return Java String/date wrappers. Preserve exact text and
    # native bool/date values; never trim, guess date formats or coerce 1 to true.
    if value is None or isinstance(value, (str, bool, int, date)):
        return value
    return str(value)


def decode_rows(table, raw_rows):
    schema = SCHEMAS[table]
    result = []
    try:
        for row in raw_rows:
            if len(row) != len(schema):
                raise ValueError("Unexpected column count")
            result.append({field: normalise(adapt_value(value, kind), kind)
                           for (field, kind), value in zip(schema, row)})
    except (ValueError, TypeError, OverflowError):
        raise VerificationFailure(f"{table}: returned values do not match the source schema.") from None
    return result


def reconcile_table(table, raw_rows, metadata):
    rows = decode_rows(table, raw_rows)
    if len(rows) != metadata["row_count"]:
        raise VerificationFailure(f"{table}: row count differs from the snapshot manifest.")
    if canonical_digest(table, rows) != metadata["canonical_sha256"]:
        raise VerificationFailure(f"{table}: canonical content hash differs (changed, missing, duplicate or extra values).")
    return rows


def joined_reference(tables):
    reports = tables["malaria_monthly"]
    logs = tables["reporting_log"]
    registry = tables["facility_registry"]
    version_key = lambda r: (r["dataset_id"], r["report_id"], r["report_version"])
    if (len({version_key(r) for r in reports}) != len(reports) or
        len({version_key(r) for r in logs}) != len(logs) or
        len({(r["dataset_id"], r["facility_id"]) for r in registry}) != len(registry)):
        raise VerificationFailure("Join acceptance requires unique report, log and registry keys.")
    log_index = {version_key(r): r for r in logs}
    facilities = {(r["dataset_id"], r["facility_id"]): r for r in registry}
    if set(log_index) != {version_key(r) for r in reports}:
        raise VerificationFailure("Join acceptance requires exactly one log per report version.")
    joined = []
    for report in reports:
        event = log_index[version_key(report)]
        facility = facilities.get((report["dataset_id"], report["facility_id"]))
        if facility is None:
            raise VerificationFailure("Join acceptance found an unknown facility.")
        joined.append(tuple(report[f] for f, _ in SCHEMAS["malaria_monthly"]) +
                      (facility["district_id"], event["received_at_utc"],
                       event["status"], event["declared_complete"]))
    return joined


def reconcile_join(raw, expected):
    schema = SCHEMAS["malaria_monthly"] + (
        ("district_id", "id"), ("received_at_utc", "timestamp"),
        ("status", "status"), ("declared_complete", "bool"),
    )
    observed = []
    try:
        for row in raw:
            if len(row) != len(schema):
                raise ValueError("Unexpected joined column count")
            observed.append(tuple(normalise(adapt_value(value, kind), kind)
                                  for (_, kind), value in zip(schema, row)))
    except (ValueError, TypeError, OverflowError):
        raise VerificationFailure("Joined values do not match the source schema.") from None
    if Counter(observed) != Counter(expected):
        raise VerificationFailure("Three-table join differs from exact expected report-version rows.")


def check_live(connect, *, jar, url, username, password, database, dataset_id,
               manifest, fixture, as_of_utc):
    # Preflight before opening any connection.
    queries = source_queries(database, dataset_id)
    expected_join = joined_reference(fixture)
    expected_analysis = analyse(fixture, as_of_utc=as_of_utc)
    connection = cursor = None
    stage = "connection"
    try:
        connection = connect(DRIVER_CLASS, url, [username, password], str(jar))
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
        if row is None or len(row) != 1 or str(row[0]) != "1":
            raise VerificationFailure("SELECT 1 did not return 1.")
        print("ZETARIS_CONNECTION=PASS", flush=True)
        observed = {}
        for table, query in queries.items():
            stage = table
            observed[table] = reconcile_table(table, read_bounded(cursor, query), manifest["tables"][table])
            print(f"ZETARIS_{table.upper()}=PASS\nZETARIS_{table.upper()}_ROWS={len(observed[table])}", flush=True)
            print(f"ZETARIS_{table.upper()}_SHA256={manifest['tables'][table]['canonical_sha256']}", flush=True)
        stage = "three-table join"
        joined = read_bounded(cursor, join_query(database, dataset_id))
        reconcile_join(joined, expected_join)
        print(f"ZETARIS_JOIN=PASS\nZETARIS_JOIN_ROWS={len(joined)}", flush=True)
        stage = "reference analysis"
        actual = analyse(observed, as_of_utc=as_of_utc)
        if actual != expected_analysis:
            raise VerificationFailure("Live-source calculations differ from the CSV reference at the same cutoff.")
        for period in ("comparison", "target"):
            for view, metrics in (("CANONICAL", actual[period]), ("RAW", actual[period]["raw"])):
                print(f"{period.upper()}_{view}_TESTED={metrics['tested']}")
                print(f"{period.upper()}_{view}_POSITIVE={metrics['positive']}")
        print(f"AS_OF_UTC={as_of_utc}\nZETARIS_REFERENCE_PARITY=PASS", flush=True)
        print("ZETARIS_SNAPSHOT=PASS", flush=True)
    except VerificationFailure:
        raise
    except Exception:
        raise VerificationFailure(f"JDBC read failed during {stage}; raw driver errors withheld. Check the local service, credentials, schema and permissions.") from None
    finally:
        for resource in (cursor, connection):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    pass


def credentials():
    username = os.environ.get("ZETARIS_USERNAME", "")
    password = os.environ.get("ZETARIS_PASSWORD", "")
    if not username.strip():
        if not sys.stdin.isatty():
            raise Blocked("Set ZETARIS_USERNAME locally or use an interactive terminal.")
        username = input("Zetaris JDBC user ID: ")
    if not password.strip():
        if not sys.stdin.isatty():
            raise Blocked("Set ZETARIS_PASSWORD locally or use an interactive terminal.")
        password = getpass.getpass("Zetaris JDBC password: ")
    if not username.strip() or not password.strip():
        raise Blocked("Non-empty credentials are required.")
    return username, password


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--as-of", default=DEFAULT_CUTOFF)
    parser.add_argument("--jar")
    parser.add_argument("--url")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--check-fixture", action="store_true", help="Offline preflight only; no JDBC PASS")
    args = parser.parse_args(argv)
    tag = "SNAPSHOT_FIXTURE" if args.check_fixture else "ZETARIS_SNAPSHOT"
    try:
        validate_scope(args.database, args.dataset)
        normalise(args.as_of, "timestamp")
        if args.env_file:
            load_env_file(args.env_file, os.environ)
        manifest, fixture = load_snapshot(ROOT / "data/synthetic" / args.dataset)
        if manifest["dataset_id"] != args.dataset:
            raise VerificationFailure("Manifest dataset ID differs from the requested snapshot.")
        joined_reference(fixture)
        if args.check_fixture:
            analyse(fixture, as_of_utc=args.as_of)
            print("SNAPSHOT_FIXTURE=PASS\nZETARIS_CONNECTION=NOT_RUN\nZETARIS_SNAPSHOT=NOT_RUN")
            return 0
        jar = validate_jar(args.jar or os.environ.get("ZETARIS_JDBC_JAR", ""))
        url = validate_url(args.url or os.environ.get("ZETARIS_JDBC_URL") or DEFAULT_URL)
        try:
            driver = importlib.import_module("jaydebeapi")
        except ImportError:
            raise Blocked("Use the existing verified JayDeBeApi/JPype environment.") from None
        username, password = credentials()
        print(f"DATASET_ID={args.dataset}\nDATABASE={args.database}", flush=True)
        print(f"MANIFEST_SHA256={hashlib.sha256((ROOT / 'data/synthetic' / args.dataset / 'manifest.json').read_bytes()).hexdigest()}")
        check_live(driver.connect, jar=jar, url=url, username=username, password=password,
                   database=args.database, dataset_id=args.dataset, manifest=manifest,
                   fixture=fixture, as_of_utc=args.as_of)
        return 0
    except Blocked as exc:
        print(f"{tag}=BLOCKED\n{exc}", file=sys.stderr)
        return 2
    except VerificationFailure as exc:
        print(f"{tag}=FAIL\n{exc}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print(f"{tag}=BLOCKED\nVerification interrupted before completion.", file=sys.stderr)
        return 2
    except Exception:
        print(f"{tag}=FAIL\nSnapshot or schema validation failed; raw errors withheld.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
