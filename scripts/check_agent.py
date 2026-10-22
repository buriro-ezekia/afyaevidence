#!/usr/bin/env python3
"""Exercise all committed snapshots with the explicitly scripted agent policy."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from afyaevidence.agent import run_agent
from afyaevidence.analysis import Request, investigate
from afyaevidence.model import ScriptedProvider
from afyaevidence.snapshot import FixtureGateway


def main():
    count=0;success=True
    for path in sorted((ROOT/'data/synthetic').glob('fx_*')):
        if path.name=='fx_probe_v1': continue
        bundle=investigate(FixtureGateway().collect(path))
        result=run_agent(bundle,ScriptedProvider())
        passed=result['execution_status']=='ready_for_review'
        print(path.name+'='+('PASS' if passed else 'FAIL'))
        success=success and passed;count+=1
    early=investigate(FixtureGateway().collect(ROOT/'data/synthetic/fx_a061c452'),Request(as_of_utc='2025-12-10T00:00:00Z'))
    passed=run_agent(early,ScriptedProvider())['execution_status']=='ready_for_review'
    success=success and passed;count+=1
    print('AGENT_FIXTURE_CHECK='+('PASS' if success and count==16 else 'FAIL'))
    print(f'AGENT_FIXTURE_CASES={count}\nMODEL_MODE=scripted\nLIVE_MODEL=NOT_RUN\nLIVE_ZETARIS=NOT_RUN\nLIVE_HMEM=NOT_RUN')
    return 0 if success and count==16 else 1


if __name__=='__main__': raise SystemExit(main())
