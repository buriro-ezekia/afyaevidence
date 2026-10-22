#!/usr/bin/env python3
"""Generate or check the versioned synthetic suite; never access a live service."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from evals.generate import main

if __name__ == "__main__":
    raise SystemExit(main())
