"""Fixed construction recipes. No expected-answer file is read by the generator."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random

from afyaevidence.contracts import ALGORITHM, SCHEMAS, canonical_digest, csv_bytes

ROOT = Path(__file__).resolve().parents[1]
VERSION = "synthetic-1.0.0"
SEED = 20261022
GENERATED_AT = "2026-10-22T00:00:00Z"
# Names remain evaluator-only. Sources and manifests expose opaque identifiers.
RECIPES = {
    "expanded_testing": "fx_10a7c921", "revision": "fx_32e8b610",
    "unexplained": "fx_47c9d203", "mixed": "fx_58f1a946",
    "missing_baseline": "fx_6b2d801e", "zero_denominator": "fx_7c3e912f",
    "impossible_counts": "fx_8d4fa230", "conflicting_key": "fx_9e50b341",
    "delayed_revision": "fx_a061c452", "latest_invalid": "fx_b172d563",
    "latest_withdrawn": "fx_c283e674", "missing_target": "fx_d394f785",
    "orphan_log": "fx_e4a50896", "unknown_facility": "fx_f5b619a7",
    "missing_count": "fx_06c72ab8",
}
MONTHS = [f"{year}-{month:02d}-01" for year in (2024, 2025) for month in range(1, 13)]


def next_receipt(month):
    year, number = map(int, month[:7].split("-"))
    return f"{year + (number == 12)}-{number % 12 + 1:02d}-05T12:00:00Z"


def build_tables(name, dataset_id):
    # Separate fixed RNG per snapshot: iteration order cannot change a snapshot.
    rng = random.Random(SEED)
    tables = {table: [] for table in SCHEMAS}
    for i in range(1, 7):
        tables["facility_registry"].append(dict(
            dataset_id=dataset_id, facility_id=f"F{i:03d}", district_id="D001",
            facility_type="health_centre" if i <= 2 else "dispensary",
            active_from="2024-01-01", active_to=None,
        ))
    for month in MONTHS:
        for i in range(6):
            tested = rng.randint(40, 100)
            positive = tested // 5
            if month in {"2025-10-01", "2025-11-01"}:
                tested = [100, 100, 100, 100, 50, 50][i]
                positive = [20, 20, 20, 20, 10, 10][i]
                if name == "expanded_testing":
                    tested = [80, 80, 60, 60, 60, 60][i]
                    positive = [16, 16, 12, 12, 12, 12][i]
                    if month == "2025-11-01":
                        tested *= 2
                        positive *= 2
                elif month == "2025-11-01":
                    if name == "unexplained":
                        positive = [35, 35, 35, 35, 18, 17][i]
                    elif name == "mixed":
                        positive = [20, 25, 25, 25, 15, 15][i]
                    elif name == "zero_denominator":
                        tested = positive = 0
            report_id = f"R{month[:7].replace('-', '')}{i+1:03d}"
            tables["malaria_monthly"].append(dict(
                dataset_id=dataset_id, report_id=report_id, report_version=1,
                facility_id=f"F{i+1:03d}", period_month=month,
                suspected_episodes=tested + 20, tested_episodes=tested,
                positive_episodes=positive,
            ))
            tables["reporting_log"].append(dict(
                dataset_id=dataset_id, report_id=report_id, report_version=1,
                received_at_utc=next_receipt(month), status="accepted",
                declared_complete=True,
            ))
    reports, logs = tables["malaria_monthly"], tables["reporting_log"]
    target = next(row for row in reports if row["report_id"] == "R202511001")
    event = next(row for row in logs if row["report_id"] == target["report_id"])
    if name in {"revision", "mixed", "delayed_revision", "latest_invalid", "latest_withdrawn"}:
        revision, receipt = deepcopy(target), deepcopy(event)
        revision["report_version"] = receipt["report_version"] = 2
        revision["suspected_episodes"] += 5
        receipt["received_at_utc"] = "2025-12-07T12:00:00Z"
        if name == "delayed_revision":
            revision["positive_episodes"] = 35
            receipt["received_at_utc"] = "2025-12-20T12:00:00Z"
        elif name == "latest_invalid":
            revision["positive_episodes"] = 101
        elif name == "latest_withdrawn":
            receipt["status"] = "withdrawn"
        reports.append(revision)
        logs.append(receipt)
    elif name == "missing_baseline":
        removed = {r["report_id"] for r in reports if r["period_month"] == "2025-10-01"}
        reports[:] = [r for r in reports if r["report_id"] not in removed]
        logs[:] = [r for r in logs if r["report_id"] not in removed]
    elif name == "missing_target":
        reports.remove(target)
        logs.remove(event)
    elif name == "impossible_counts":
        target["positive_episodes"] = 101
    elif name == "conflicting_key":
        conflict = deepcopy(target)
        conflict["positive_episodes"] = 21
        reports.append(conflict)
    elif name == "orphan_log":
        orphan = deepcopy(event)
        orphan["report_id"] = "R202511999"
        logs.append(orphan)
    elif name == "unknown_facility":
        target["facility_id"] = "F999"
    elif name == "missing_count":
        target["positive_episodes"] = None
    return tables


def artifacts():
    result = {}
    for name, dataset_id in RECIPES.items():
        tables = build_tables(name, dataset_id)
        manifest = dict(
            dataset_id=dataset_id, schema_version="aggregate-1", generator_version=VERSION,
            seed=SEED, generation_timestamp=GENERATED_AT, synthetic=True,
            canonical_algorithm=ALGORITHM,
            scope=dict(district_id="D001", first_month=MONTHS[0], last_month=MONTHS[-1],
                       facility_count=6, expected_facility_months=144),
            tables={},
        )
        directory = f"data/synthetic/{dataset_id}"
        for table, rows in tables.items():
            content = csv_bytes(table, rows)
            result[f"{directory}/{table}.csv"] = content
            manifest["tables"][table] = dict(
                file=f"{table}.csv", field_order=[field for field, _ in SCHEMAS[table]],
                row_count=len(rows), byte_sha256=hashlib.sha256(content).hexdigest(),
                canonical_sha256=canonical_digest(table, rows),
            )
        result[f"{directory}/manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare every published byte; write nothing")
    args = parser.parse_args(argv)
    contents = artifacts()
    if args.check:
        failures = [name for name, data in contents.items()
                    if not (ROOT / name).is_file() or (ROOT / name).read_bytes() != data]
        # Each snapshot must contain exactly its four declared files.
        for dataset_id in RECIPES.values():
            directory = ROOT / "data/synthetic" / dataset_id
            if directory.exists():
                failures.extend(str(p.relative_to(ROOT)) for p in directory.iterdir()
                                if str(p.relative_to(ROOT)) not in contents)
        if failures:
            print("SYNTHETIC_REPRODUCIBILITY=FAIL")
            for name in failures:
                print(name)
            return 1
        print(f"SYNTHETIC_REPRODUCIBILITY=PASS\nSYNTHETIC_SNAPSHOTS={len(RECIPES)}")
        return 0
    for name, content in contents.items():
        path = ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    print(f"SYNTHETIC_GENERATED=PASS\nSYNTHETIC_SNAPSHOTS={len(RECIPES)}\nLIVE_ZETARIS=NOT_RUN")
    return 0
