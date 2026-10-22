#!/usr/bin/env python3
"""Run tests with durable logs and a real exit status; no credentials or live providers.

Default: complete repository unittest suite. --focused: only the added slice.
--fixtures: also execute existing deterministic scripts and isolated wheel checks.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--focused',action='store_true')
    p.add_argument('--fixtures',action='store_true')
    a=p.parse_args()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    logs=ROOT/'runtime'/('identity-verification-'+stamp);logs.mkdir(parents=True)
    env=dict(os.environ);env['PYTHONPATH']=str(ROOT/'src')+os.pathsep+str(ROOT/'tests')
    for key in ('AFYA_REVIEW_TOKEN','AFYA_OIDC_CLIENT_SECRET','ZETARIS_PASSWORD'):env.pop(key,None)
    versions={}
    for package in ('PyJWT','cryptography'):
        try:versions[package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            print('DEPENDENCY_MISSING='+package+'; install requirements-identity.txt');return 2
    commands=[]
    if a.focused:
        for pattern in ('test_identity_*.py','test_managed_worker.py'):
            commands.append([sys.executable,'-m','unittest','discover','-s','tests','-p',pattern,'-v'])
    else:commands.append([sys.executable,'-m','unittest','discover','-s','tests','-v'])
    if a.fixtures:
        for script,args in [('generate_probe.py',['--check']),('verify_zetaris.py',['--check-fixture']),
                ('generate_synthetic.py',['--check']),('evaluate_synthetic.py',[]),
                ('verify_zetaris_snapshot.py',['--check-fixture']),('check_agent.py',[]),('verify_hmem.py',[])]:
            commands.append([sys.executable,'scripts/'+script,*args])
        commands.append([sys.executable,'-m','pip','wheel','.', '--no-deps','--wheel-dir',str(logs/'wheel')])
        commands.append([sys.executable,'scripts/check_runtime_package.py',str(logs/'wheel/afyaevidence-0.1.0-py3-none-any.whl'),
                         '--smoke-snapshot','data/synthetic/fx_32e8b610'])
    metadata=dict(python=sys.version,executable=sys.executable,dependencies=versions,
                  focused=a.focused,fixtures=a.fixtures,checks=[],live_oidc='NOT_RUN',live_systemd='NOT_RUN',live_jdbc='NOT_RUN')
    for flag,name in [(['rev-parse','HEAD'],'git_head'),(['status','--short'],'git_status')]:
        result=subprocess.run(['git',*flag],cwd=ROOT,capture_output=True,text=True)
        metadata[name]=result.stdout.strip() if result.returncode==0 else 'unavailable'
    metadata['source_sha256']={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted((ROOT/'src/afyaevidence').glob('*.py'))}
    exit_code=0
    for index,cmd in enumerate(commands,1):
        path=logs/f'check-{index:02d}.log'
        print('RUNNING_CHECK='+str(index),flush=True)
        with path.open('x',encoding='utf-8') as log:
            process=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            for line in process.stdout:
                print(line,end='');log.write(line)
            code=process.wait()
        metadata['checks'].append(dict(command=cmd,exit_code=code,log=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        if code!=0:exit_code=code;break
    (logs/'verification.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print('IDENTITY_WORKER_TESTS='+('PASS' if exit_code==0 else 'FAIL'))
    print('VERIFICATION_DIR='+str(logs))
    return exit_code

if __name__=='__main__':raise SystemExit(main())
