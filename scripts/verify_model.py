#!/usr/bin/env python3
"""Check one explicit local Ollama endpoint and strict-action generation; no data access."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from afyaevidence.agent import parse_action
from afyaevidence.model import OllamaProvider


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--endpoint',default=os.environ.get('OLLAMA_BASE_URL','http://127.0.0.1:8082'))
    p.add_argument('--model',default=os.environ.get('OLLAMA_MODEL','qwen2.5:3b'))
    p.add_argument('--list-models',action='store_true')
    p.add_argument('--output',type=Path)
    args=p.parse_args(argv)
    receipt=dict(schema_version='model-probe-1',status='FAIL',provider='ollama',model=args.model)
    try:
        if args.output and args.output.exists(): raise ValueError('Output exists')
        provider=OllamaProvider(endpoint=args.endpoint,model=args.model)
        names=provider.models()
        for name in names: print('OLLAMA_MODEL='+name)
        if args.list_models:
            print('OLLAMA_LIST=PASS\nLIVE_MODEL=NOT_RUN')
            return 0
        if args.model not in names: raise ValueError('Requested model is not installed')
        response=provider.next_action([dict(role='system',content='Return only the requested JSON action; no additional text.'),
            dict(role='user',content='Return exactly: {"type":"tool_call","tool":"compare_matched_facilities","arguments":{"include_contributions":false}}')],timeout=180)
        expected=dict(type='tool_call',tool='compare_matched_facilities',arguments=dict(include_contributions=False))
        if parse_action(response['content'])!=expected: raise ValueError('Strict-action check failed')
        receipt.update(status='PASS',response=response,checked_at_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
        print('OLLAMA_STRICT_ACTION=PASS\nLIVE_MODEL=PASS\nAGENT_REASONING=NOT_RUN')
        code=0
    except (Exception,KeyboardInterrupt):
        print('OLLAMA_STRICT_ACTION=FAIL\nCheck the explicit endpoint, installed model and strict JSON capability; no fallback.',file=sys.stderr)
        code=1
    if args.output:
        try:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            with args.output.open('x',encoding='utf-8') as stream: json.dump(receipt,stream,indent=2);stream.write('\n')
        except OSError:
            print('MODEL_RECEIPT=NOT_SAVED',file=sys.stderr)
            return 1
    return code


if __name__=='__main__': raise SystemExit(main())
