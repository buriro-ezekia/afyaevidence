#!/usr/bin/env python3
"""Explicit real-systemd tests using a harmless temporary agent, never health data.

--run is required. A missing user manager/cgroup capability exits BLOCKED (2).
Tests cancellation, orphan session descendants, abrupt launcher death and timeout.
"""
from contextlib import closing
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from afyaevidence.identity_auth import Principal
from afyaevidence import managed_worker as mw

PROBE = '''import argparse,json,os,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a,_=p.parse_known_args()
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'],start_new_session=True)
Path(a.output+'.pids').write_text(json.dumps([os.getpid(),child.pid]))
while True: time.sleep(.1)
'''


def wait_pids(state):
    end=time.monotonic()+30
    while time.monotonic()<end:
        matches=list(state.glob('*.pids'))
        if matches:return json.loads(matches[-1].read_text())
        time.sleep(.1)
    raise AssertionError('probe did not start; inspect job audit/resource-controller delegation')


def exited(pid):
    try:
        text=(Path('/proc')/str(pid)/'stat').read_text()
        return text[text.rfind(')')+2:].split()[0] in ('Z','X')
    except FileNotFoundError:return True


def main():
    if sys.argv[1:]!=['--run']:
        print('Usage: python scripts/check_managed_systemd.py --run');return 2
    backend=mw.SystemdBackend()
    try:backend.preflight()
    except mw.Blocked as exc:
        print('LIVE_SYSTEMD=BLOCKED\nREASON='+str(exc));return 2
    with tempfile.TemporaryDirectory(prefix='afya-systemd-check-') as temp:
        root=Path(temp);project=root/'project';package=project/'src/afyaevidence';package.mkdir(parents=True)
        (package/'__init__.py').write_text('');(package/'agent_cli.py').write_text(PROBE)
        args=['--data-mode','fixture','--snapshot','unused','--model-provider','scripted']
        states=[];launcher=None;thread=None;cancel=threading.Event();results={}
        try:
            state=root/'cancel';states.append(state)
            def run():
                try:results['cancel']=mw.run_job(state,project,args,backend=backend,seconds=20,cancel=cancel)
                except BaseException as exc:results['error']=type(exc).__name__
            thread=threading.Thread(target=run);thread.start()
            pids=wait_pids(state);cancel.set();thread.join(timeout=30)
            assert not thread.is_alive() and results.get('cancel',{}).get('state')=='cancelled',results
            assert all(exited(p) for p in pids),'session-escaping descendant survived cancellation'
            print('SYSTEMD_CANCEL_DESCENDANTS=PASS')

            state=root/'kill';states.append(state)
            env={k:v for k,v in os.environ.items() if k not in ('AFYA_REVIEW_TOKEN','AFYA_OIDC_CLIENT_SECRET','ZETARIS_PASSWORD')}
            env['PYTHONPATH']=str(ROOT/'src')
            launcher=subprocess.Popen([sys.executable,'-m','afyaevidence.managed_worker','run',
                '--state-dir',str(state),'--project',str(project),'--timeout','20','--',*args],
                env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            pids=wait_pids(state);launcher.kill();launcher.wait(timeout=5)
            try:mw.run_job(state,project,args,backend=backend,seconds=20)
            except mw.Blocked as exc:assert str(exc)=='prior_job_requires_reconciliation'
            else:raise AssertionError('replacement started after abrupt launcher death')
            report=mw.audit(state)['jobs'][0]
            result=mw.reconcile(state,report['job_id'],principal=Principal('https://fixture.invalid','integration-test',('administrator',)),
                expected_revision=report['revision'],event_key='integration_recovery',reason='Synthetic containment test after launcher SIGKILL.',backend=backend)
            assert result['state']=='reconciled_failed'
            assert all(exited(p) for p in pids),'descendant survived recovery'
            print('SYSTEMD_SIGKILL_RECOVERY=PASS')

            state=root/'timeout';states.append(state)
            result=mw.run_job(state,project,args,backend=backend,seconds=2)
            assert result['state']=='failed',result
            assert all(exited(p) for p in wait_pids(state))
            print('SYSTEMD_RUNTIME_LIMIT=PASS\nLIVE_SYSTEMD=PASS\nLIVE_JDBC=NOT_RUN\nLIVE_MODEL=NOT_RUN')
            return 0
        finally:
            cancel.set()
            if launcher and launcher.poll() is None:launcher.kill();launcher.wait(timeout=5)
            for state in states:
                try:
                    for job in mw.audit(state)['jobs']:backend.stop_and_confirm(job['unit'],job['cgroup'])
                except Exception:print('CLEANUP_REQUIRES_OPERATOR_INSPECTION='+str(state),file=sys.stderr)
            if thread:thread.join(timeout=15)

if __name__=='__main__':raise SystemExit(main())
