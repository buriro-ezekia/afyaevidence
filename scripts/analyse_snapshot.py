#!/usr/bin/env python3
"""Run the packaged deterministic layer from the existing checkout."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from afyaevidence.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
