from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from afyaevidence.identity_auth import Principal,IdentityError
from afyaevidence import managed_worker as mw
from identity_support import ISSUER


class FakeBackend:
    """Service-manager test double; never counted as live cgroup verification."""
    def __init__(self):
        self.commands=[];self.fail_start=False;self.fail_cleanup=False;self.running=False
        self.limits_ok=True;self.valid_receipt=True;self.secret_seen=None
    def preflight(self):return {'status':'SIMULATED'}
    def start(self,unit,launch,cwd,seconds,memory_bytes,tasks,cpu_percent):
        self.commands.append(unit)
        if self.fail_start:raise mw.Blocked('service_start_failed')
        config=json.loads(launch.read_text());self.env=config['env']
        self.argv=config['argv'];self.launch_mode=launch.stat().st_mode & 0o777
        if self.valid_receipt:
            output=Path(config['argv'][-1]);args=dict(zip(config['argv'][3:-2:2],config['argv'][4:-2:2]))
            output.write_text(json.dumps(dict(execution_status='ready_for_review',data_mode=args['--data-mode'],
                model_mode=args['--model-provider'],memory_mode=args.get('--memory','disabled_fixture'),
                candidate_brief=dict(approval=None,review_status='awaiting_human_review',semantic_review_required=True))))
    def status(self,unit):return dict(LoadState='loaded',ActiveState='active',SubState='running' if self.running else 'exited',
        Result='success',ExecMainStatus='0',ControlGroup='/user.slice/test-'+unit,MainPID='123')
    def verify_limits(self,*args):
        if not self.limits_ok:raise mw.Blocked('resource_limits_not_effective')
    def stop_and_confirm(self,*args):
        if self.fail_cleanup:raise mw.Blocked('cgroup_cleanup_unconfirmed')
        self.running=False


class ManagedWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.project=self.root/'project';p=self.project/'src/afyaevidence';p.mkdir(parents=True)
        (p/'agent_cli.py').write_text('# test only')
        self.state=self.root/'state';self.backend=FakeBackend()
        self.args=['--data-mode','fixture','--snapshot','synthetic','--model-provider','scripted']
        self.admin=Principal(ISSUER,'admin-person',('administrator',))

    def run_job(self):return mw.run_job(self.state,self.project,self.args,backend=self.backend)

    def test_success_receipt_and_final_event_bound(self):
        result=self.run_job()
        self.assertEqual(result['state'],'ready_for_review')
        self.assertEqual([e['state'] for e in result['events']],['intent','running','ready_for_review'])
        self.assertEqual(len(result['receipt_sha256']),64)
        self.assertFalse(list(self.state.glob('*.launch.json')))

    def test_worker_environment_excludes_reviewer_secrets(self):
        with patch.dict(os.environ,{'AFYA_REVIEW_TOKEN':'do-not-forward','AFYA_OIDC_CLIENT_SECRET':'never-forward','PYTHONSTARTUP':'bad'}):
            self.run_job()
        self.assertNotIn('AFYA_REVIEW_TOKEN',self.backend.env)
        self.assertNotIn('AFYA_OIDC_CLIENT_SECRET',self.backend.env)
        self.assertNotIn('PYTHONSTARTUP',self.backend.env)
        self.assertEqual(self.backend.launch_mode,0o600)

    def test_uncertain_start_keeps_admission_blocked(self):
        self.backend.fail_start=True
        self.assertEqual(self.run_job()['state'],'needs_operator_reconciliation')
        self.backend.fail_start=False
        with self.assertRaisesRegex(mw.Blocked,'prior_job_requires_reconciliation'):self.run_job()
        self.assertEqual(len(self.backend.commands),1)

    def test_cleanup_failure_is_not_success(self):
        self.backend.fail_cleanup=True
        self.assertEqual(self.run_job()['state'],'needs_operator_reconciliation')

    def test_cancel_retains_receipt_without_review_approval(self):
        event=threading.Event();event.set();self.backend.running=True
        result=mw.run_job(self.state,self.project,self.args,backend=self.backend,cancel=event)
        self.assertEqual(result['state'],'cancelled')
        self.assertTrue(list(self.state.glob('*.receipt.json')))

    def test_resource_limits_must_be_effective(self):
        self.backend.limits_ok=False
        self.assertEqual(self.run_job()['state'],'needs_operator_reconciliation')

    def test_exit_zero_without_receipt_is_failure(self):
        self.backend.valid_receipt=False
        self.assertEqual(self.run_job()['state'],'failed')

    def test_lock_contention_prevents_dispatch(self):
        root=mw.private_state(self.state)
        with mw.ownership(root):
            with self.assertRaisesRegex(mw.Blocked,'worker_busy'):self.run_job()
        self.assertEqual(self.backend.commands,[])

    def test_argument_and_resource_limits(self):
        for args in (['--output','x'],self.args+['--model-provider','ollama'],self.args+['--shell','sh']):
            with self.subTest(args=args),self.assertRaises(ValueError):mw.validate_args(args)
        with self.assertRaises(ValueError):mw.run_job(self.state,self.project,self.args,backend=self.backend,seconds=True)
        self.assertFalse(self.state.exists())

    def test_private_directory_required(self):
        self.state.mkdir(mode=0o755)
        with self.assertRaisesRegex(mw.Blocked,'owner_only'):mw.private_state(self.state)

    def test_audit_empty_not_recovery_claim_and_read_only(self):
        self.assertEqual(mw.audit(self.state),dict(state='NO_MANAGED_STATE',jobs=[]))
        self.assertFalse(self.state.exists())
        result=self.run_job()
        report=mw.audit(self.state)
        self.assertEqual(report['state'],'FINALISED');self.assertEqual(len(report['jobs']),1)
        with closing(sqlite3.connect(self.state/'managed.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],3)

    def test_admin_recovery_is_audited_idempotent_and_never_replays(self):
        self.backend.fail_start=True;result=self.run_job();self.backend.fail_start=False
        args=dict(principal=self.admin,expected_revision=result['revision'],event_key='recover_1',reason='Investigated the stopped synthetic worker.',backend=self.backend)
        recovered=mw.reconcile(self.state,result['job_id'],**args)
        self.assertEqual(recovered['state'],'reconciled_failed')
        self.assertEqual(mw.reconcile(self.state,result['job_id'],**args),recovered)
        self.assertEqual(len(self.backend.commands),1)
        with closing(mw.database(self.state)) as db:
            actor=json.loads(db.execute('SELECT actor_json FROM recoveries').fetchone()[0])
            self.assertEqual(actor['subject'],'admin-person')

    def test_lost_recovery_acknowledgement_does_not_replay(self):
        self.backend.fail_start=True;result=self.run_job();self.backend.fail_start=False
        args=dict(principal=self.admin,expected_revision=result['revision'],event_key='ack',
                  reason='Recover a synthetic interrupted execution.',backend=self.backend)
        first=mw.reconcile(self.state,result['job_id'],**args)
        with closing(mw.database(self.state)) as db:
            db.execute('UPDATE recoveries SET result_json=NULL')
        self.assertEqual(mw.reconcile(self.state,result['job_id'],**args),first)
        self.assertEqual(len(self.backend.commands),1)

    def test_non_admin_cannot_recover(self):
        self.backend.fail_start=True;result=self.run_job()
        with self.assertRaises(IdentityError):mw.reconcile(self.state,result['job_id'],principal=Principal(ISSUER,'r',('reviewer',)),expected_revision=result['revision'],event_key='no',reason='Please reconcile this synthetic job.',backend=self.backend)

    def test_failed_recovery_never_unblocks_admission(self):
        self.backend.fail_start=True;result=self.run_job();self.backend.fail_cleanup=True
        with self.assertRaises(mw.Blocked):mw.reconcile(self.state,result['job_id'],principal=self.admin,expected_revision=result['revision'],event_key='bad',reason='Investigating unexpected service state.',backend=self.backend)
        with self.assertRaises(mw.Blocked):self.run_job()

    def test_manager_command_is_service_not_process_group_only(self):
        backend=mw.SystemdBackend();backend.run_binary='/usr/bin/systemd-run'
        class Reply:returncode=0
        with patch('afyaevidence.managed_worker._command',return_value=Reply()) as call:
            backend.start('afya-test.service',self.root/'launch.json',self.project,660,2147483648,128,100)
        cmd=call.call_args.args[0]
        for flag in ('--property=KillMode=control-group','--property=Delegate=no','--property=NoNewPrivileges=yes',
                     '--expand-environment=no','--property=RuntimeMaxSec=660s','--property=MemoryMax=2147483648'):
            self.assertIn(flag,cmd)
        self.assertNotIn('--scope',cmd)
        self.assertNotIn('--collect',cmd)

if __name__=='__main__':unittest.main()
