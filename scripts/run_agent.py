#!/usr/bin/env python3
"""Run the packaged bounded agent from the existing checkout."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from afyaevidence.agent_cli import main

if __name__=='__main__': raise SystemExit(main())
