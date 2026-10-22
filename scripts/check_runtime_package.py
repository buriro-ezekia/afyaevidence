#!/usr/bin/env python3
"""Reject a runtime wheel containing evaluator code, data or local credentials."""
import argparse
from pathlib import Path
import zipfile


def check(path):
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        allowed = {"afyaevidence/__init__.py", "afyaevidence/contracts.py"}
        required_meta = {"METADATA", "WHEEL", "top_level.txt", "RECORD"}
        for name in names:
            parts = name.split("/")
            if name in allowed:
                continue
            if (len(parts) == 2 and parts[0].startswith("afyaevidence-") and
                parts[0].endswith(".dist-info") and parts[1] in required_meta):
                continue
            raise ValueError(f"Unexpected runtime member: {name}")
        if not allowed <= names:
            raise ValueError("Runtime contract package missing")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    try:
        check(args.wheel)
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        print(f"RUNTIME_PACKAGE=FAIL: {exc}")
        return 1
    print("RUNTIME_PACKAGE=PASS\nEVALUATOR_KEYS_IN_WHEEL=NO\nSOURCE_DATA_IN_WHEEL=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
