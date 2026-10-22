#!/usr/bin/env python3
"""Compare local synthetic snapshots with evaluator-only independent expectations."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from evals.evaluate import main

if __name__ == "__main__":
    raise SystemExit(main())
