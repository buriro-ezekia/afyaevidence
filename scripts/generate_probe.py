#!/usr/bin/env python3
"""Reproduce the small synthetic source-access fixture without external packages."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "data" / "synthetic" / "probe"
FIELDS = ["dataset_id", "facility_id", "district_id", "facility_type", "active_from", "active_to"]


def fixture_bytes() -> tuple[bytes, bytes]:
    rows = [
        ["fx_probe_v1", f"F{number:03d}", "D001",
         "health_centre" if number <= 2 else "dispensary", "2024-01-01", ""]
        for number in range(1, 7)
    ]
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(FIELDS)
    writer.writerows(rows)
    csv_bytes = buffer.getvalue().encode("utf-8")
    canonical_rows = sorted(
        json.dumps(row[:-1] + [None], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        for row in rows
    )
    canonical = b"".join(row + b"\n" for row in canonical_rows)
    manifest = {
        "dataset_id": "fx_probe_v1",
        "schema_version": "probe-1",
        "purpose": "synthetic JDBC source-access probe; no malaria counts",
        "generation_timestamp": "2026-10-21T00:00:00Z",
        "canonical_algorithm": "afya-canonical-rows-v1",
        "tables": {
            "facility_registry": {
                "file": "facility_registry.csv",
                "field_order": FIELDS,
                "row_count": len(rows),
                "byte_sha256": hashlib.sha256(csv_bytes).hexdigest(),
                "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
            }
        },
    }
    return csv_bytes, (json.dumps(manifest, indent=2) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check existing bytes without writing.")
    args = parser.parse_args()
    contents = dict(zip(("facility_registry.csv", "manifest.json"), fixture_bytes()))
    if args.check:
        for name, expected in contents.items():
            path = DESTINATION / name
            if not path.is_file() or path.read_bytes() != expected:
                print(f"PROBE_REPRODUCIBILITY=FAIL: {name} differs; regenerate explicitly.")
                return 1
        print("PROBE_REPRODUCIBILITY=PASS")
        return 0
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for name, content in contents.items():
        (DESTINATION / name).write_bytes(content)
    print("PROBE_GENERATED=PASS: six fictional facility rows; no live query performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
