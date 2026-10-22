#!/usr/bin/env python3
"""Exercise both execution profiles with the explicitly scripted agent policy."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from afyaevidence.agent import EXECUTION_PROFILES, run_agent
from afyaevidence.analysis import Request, investigate
from afyaevidence.model import ScriptedProvider
from afyaevidence.snapshot import FixtureGateway


def main():
    cases=[];success=True;executions=0
    for path in sorted((ROOT/'data/synthetic').glob('fx_*')):
        if path.name=='fx_probe_v1': continue
        cases.append((path.name,investigate(FixtureGateway().collect(path))))
    early=investigate(FixtureGateway().collect(ROOT/'data/synthetic/fx_a061c452'),Request(as_of_utc='2025-12-10T00:00:00Z'))
    cases.append(('fx_a061c452_earlier_cutoff',early))
    for profile in EXECUTION_PROFILES:
        profile_passed=True
        for name,bundle in cases:
            result=run_agent(bundle,ScriptedProvider(),execution_profile=profile)
            brief=result['candidate_brief']
            passed=(result['execution_status']=='ready_for_review' and result['model_mode']=='scripted' and
                    result['execution_profile']==profile and result['review_status']=='awaiting_human_review' and
                    brief is not None and brief['semantic_review_required'] is True and brief['approval'] is None and
                    (profile!='cpu' or result['model_calls']==2))
            print(profile+':'+name+'='+('PASS' if passed else 'FAIL'))
            profile_passed=profile_passed and passed;executions+=1
        print('AGENT_PROFILE_'+profile.upper()+'='+('PASS' if profile_passed else 'FAIL'))
        success=success and profile_passed
    success=success and len(cases)==16 and executions==32
    print('AGENT_FIXTURE_CHECK='+('PASS' if success else 'FAIL'))
    print(f'AGENT_FIXTURE_CASES={len(cases)}\nAGENT_FIXTURE_EXECUTIONS={executions}')
    print('EXECUTION_PROFILES='+','.join(EXECUTION_PROFILES))
    print('MODEL_MODE=scripted\nLIVE_MODEL=NOT_RUN\nLIVE_ZETARIS=NOT_RUN\nLIVE_HMEM=NOT_RUN')
    return 0 if success else 1


if __name__=='__main__': raise SystemExit(main())
