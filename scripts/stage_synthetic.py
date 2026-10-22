#!/usr/bin/env python3
"""Copy one verified source snapshot to a new upload folder, without evaluator files."""
import argparse
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from evals.reference import load_snapshot


def stage(dataset_id, destination):
    if not re.fullmatch(r"fx_[0-9a-f]{8}", dataset_id):
        raise ValueError("Use an opaque dataset ID listed in the synthetic-data guide")
    source = ROOT / "data/synthetic" / dataset_id
    manifest, _ = load_snapshot(source)
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Destination already exists; choose a new upload folder")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Validate before copying; only known CSV files and their manifest leave the repo.
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix="afya-stage-") as temp:
        staged = Path(temp) / "snapshot"
        staged.mkdir()
        for filename in [f"{table}.csv" for table in manifest["tables"]] + ["manifest.json"]:
            shutil.copyfile(source / filename, staged / filename)
        load_snapshot(staged)
        # An empty destination created concurrently is also refused.
        destination.mkdir()
        try:
            for path in staged.iterdir():
                shutil.copyfile(path, destination / path.name)
        except OSError:
            # Keep partial output visible for inspection; never claim successful staging.
            raise
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        destination = stage(args.dataset, args.destination)
    except (ValueError, OSError, KeyError) as exc:
        print(f"SYNTHETIC_STAGE=FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"SYNTHETIC_STAGE=PASS\nUPLOAD_FOLDER={destination}\nLIVE_ZETARIS=NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
