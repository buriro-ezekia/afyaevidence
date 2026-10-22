"""Operator CLI for scripted or actual-model investigations; never auto-fallback."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import sys

from .agent import Budget, EXECUTION_PROFILES, run_agent
from .analysis import Request, investigate
from .jdbc import DEFAULT_URL, JdbcGateway
from .model import OllamaProvider, ScriptedProvider
from .snapshot import FixtureGateway


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-mode',required=True,choices=('fixture','zetaris'))
    p.add_argument('--snapshot',required=True,type=Path)
    p.add_argument('--model-provider',required=True,choices=('scripted','ollama'))
    p.add_argument('--execution-profile',choices=EXECUTION_PROFILES,default='standard',
                   help='cpu: host baselines, one model-selected follow-up, then one brief-only request')
    p.add_argument('--endpoint',default=os.environ.get('OLLAMA_BASE_URL','http://127.0.0.1:8082'))
    p.add_argument('--model',default=os.environ.get('OLLAMA_MODEL','qwen2.5:3b'))
    p.add_argument('--model-timeout',type=int,metavar='SECONDS',
                   help='Per-request timeout, 1..300 seconds (cpu default 300, standard 180); bounded by remaining time')
    p.add_argument('--memory',choices=('disabled_fixture','hmem_reference'),default='disabled_fixture')
    p.add_argument('--memory-root',type=Path,default=Path('runtime/memory'))
    p.add_argument('--reviews-db',type=Path,default=Path('runtime/review-notes.sqlite3'))
    p.add_argument('--bridge-dir',type=Path,help='Explicit host integration directory containing helper/upstream')
    p.add_argument('--memory-as-of')
    p.add_argument('--database',default='AFYAEVIDENCE_REVISION')
    p.add_argument('--jar',default=os.environ.get('ZETARIS_JDBC_JAR',''))
    p.add_argument('--url',default=os.environ.get('ZETARIS_JDBC_URL',DEFAULT_URL))
    p.add_argument('--comparison-month',default='2025-10-01')
    p.add_argument('--target-month',default='2025-11-01')
    p.add_argument('--as-of',default='2026-01-15T00:00:00Z')
    p.add_argument('--question',default='Investigate the reporting change and identify the next evidence checks.')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(argv)
    if args.output.exists():
        print('AGENT_EXECUTION=FAIL\nOutput exists; choose a new receipt path.',file=sys.stderr)
        return 1
    result=dict(schema_version='agent-run-1',execution_status='failed',failure_reason='setup_failed',
                data_mode=args.data_mode,model_mode=args.model_provider,memory_mode=args.memory,
                execution_profile=args.execution_profile)
    stage='configuration'
    try:
        budget=Budget(model_timeout_seconds=args.model_timeout if args.model_timeout is not None else
                      300 if args.execution_profile=='cpu' else 180)
        request=Request(comparison_month=args.comparison_month,target_month=args.target_month,as_of_utc=args.as_of)
        if not 1<=len(args.question)<=1000: raise ValueError('Question exceeds scope')
        memory_cutoff=args.memory_as_of or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        provider=ScriptedProvider() if args.model_provider=='scripted' else OllamaProvider(endpoint=args.endpoint,model=args.model)
        if args.data_mode=='fixture':
            gateway=FixtureGateway()
        else:
            password=os.environ.get('ZETARIS_PASSWORD','')
            if not password:
                if not sys.stdin.isatty(): raise ValueError('Interactive credentials required')
                password=getpass.getpass('Zetaris JDBC password: ')
            gateway=JdbcGateway(jar=args.jar,password=password,database=args.database,url=args.url,
                                username=os.environ.get('ZETARIS_USERNAME','admin@zetaris.com'))
        stage='source_collection'
        snapshot=gateway.collect(args.snapshot)
        stage='deterministic_analysis'
        bundle=investigate(snapshot,request)
        result['evidence_bundle']=bundle.to_dict()
        with ExitStack() as stack:
            recall=None
            if args.memory=='hmem_reference':
                stage='memory_setup'
                if args.bridge_dir is None: raise ValueError('Explicit bridge directory required')
                from .memory import HmemBridge, ReviewStore, Scope
                bridge=stack.enter_context(HmemBridge(root=args.memory_root,bridge_dir=args.bridge_dir,
                    scope=Scope('afya-synthetic-v1',request.district_id),reviews=ReviewStore(args.reviews_db)))
                recall=bridge.recall
            stage='agent_execution'
            result=run_agent(bundle,provider,question=args.question,recall=recall,budget=budget,
                             execution_profile=args.execution_profile,
                             memory_as_of_utc=memory_cutoff if recall else None)
    except KeyboardInterrupt:
        result['failure_reason']='cancelled';result['execution_status']='cancelled'
        result['failure_stage']=stage
    except Exception:
        result['failure_reason']='source_model_or_memory_setup_failed'
        result['failure_stage']=stage
    try:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x',encoding='utf-8') as stream: json.dump(result,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write('\n')
    except Exception:
        print('AGENT_RECEIPT=NOT_SAVED',file=sys.stderr)
        return 1
    ready=result['execution_status']=='ready_for_review'
    print(f"DATA_MODE={args.data_mode}\nMODEL_MODE={args.model_provider}\nMEMORY_MODE={args.memory}")
    print(f"AGENT_EXECUTION={'PASS' if ready else 'FAIL'}\nEXECUTION_STATUS={result['execution_status']}")
    for key in ('prompt_version','execution_profile','model_calls','model_call_limit','tool_calls','repairs',
                'model_timeout_seconds','deadline_seconds','brief_reserve_seconds'):
        if key in result: print(key.upper()+'='+str(result[key]))
    if ready:
        brief=result['candidate_brief']
        print(f"EXPLANATION={brief['explanation']}\nREVIEW_STATUS=awaiting_human_review")
        print('LIVE_MODEL='+('PASS' if args.model_provider=='ollama' else 'NOT_RUN'))
        print('LIVE_ZETARIS='+('PASS' if args.data_mode=='zetaris' else 'NOT_RUN'))
        print('LIVE_HMEM='+('PASS' if result['memory_reads']>0 else 'NOT_RUN'))
        print('RECALLED_NOTES='+str(len(result['reference_aliases'].get('context',{}))))
        if result.get('memory_pending_sync') is not None:
            print('MEMORY_PENDING_SYNC='+str(result['memory_pending_sync']))
    else:
        print('FAILURE_REASON='+str(result['failure_reason']))
        if 'failure_stage' in result: print('FAILURE_STAGE='+result['failure_stage'])
        for event in result.get('trace',[]):
            if event['kind']=='model': print('MODEL_RESPONSE_SECONDS='+str(event.get('elapsed_seconds')))
            elif event['kind'] in ('validation_error','provider_error'): print('ACTION_ERROR='+event['code'])
            elif event['kind']=='tool': print('COMPLETED_TOOL='+event['name'])
    print(f'RECEIPT={args.output}')
    return 0 if ready else 1


if __name__=='__main__': raise SystemExit(main())
