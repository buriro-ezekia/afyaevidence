#!/usr/bin/env python3
"""Create an identity-enabled SQLite backup without changing the source database."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from afyaevidence.identity_store import copy_database

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,required=True)
p.add_argument('--destination',type=Path,required=True)
a=p.parse_args()
try:
    path=copy_database(a.source,a.destination)
except Exception as exc:
    print('IDENTITY_DB_COPY=FAIL\nERROR_TYPE='+type(exc).__name__)
    raise SystemExit(1)
print('IDENTITY_DB_COPY=PASS\nORIGINAL_DB=UNCHANGED\nIDENTITY_DB='+str(path))
