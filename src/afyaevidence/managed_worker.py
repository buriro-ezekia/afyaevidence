"""Opt-in systemd user-service workers with cgroup-v2 containment and audited recovery.

No service installation, root operations, automatic replay or public HTTP start API.
A non-final durable job blocks subsequent submission, even after supervisor SIGKILL.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

from .identity_auth import Principal

FINAL = frozenset({'ready_for_review', 'failed', 'cancelled', 'reconciled_ready_for_review', 'reconciled_failed'})
ENV_ALLOW = {'PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'JAVA_HOME', 'ZETARIS_USERNAME', 'ZETARIS_PASSWORD'}
JOB_ID = re.compile(r'^mw_[a-f0-9]{32}$')
AGENT_OPTIONS = frozenset({'--data-mode', '--snapshot', '--model-provider', '--execution-profile', '--endpoint',
    '--model', '--model-timeout', '--memory', '--memory-root', '--reviews-db', '--bridge-dir', '--memory-as-of',
    '--database', '--jar', '--url', '--comparison-month', '--target-month', '--as-of', '--question'})


class Blocked(RuntimeError):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat()


def private_state(path: Path):
    path = path.expanduser()
    if path.is_symlink():
        raise Blocked('state_symlink_refused')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise Blocked('state_requires_owner_only_permissions')
    return path.resolve()


@contextmanager
def ownership(root):
    fd = os.open(root / '.managed.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Blocked('worker_busy') from None
        yield
    finally:
        os.close(fd)


def database(root):
    path = root / 'managed.sqlite3'
    if path.is_symlink():
        raise Blocked('database_symlink_refused')
    db = sqlite3.connect(path, isolation_level=None, timeout=10)
    os.chmod(path, 0o600)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=10000')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY, state TEXT NOT NULL, revision INTEGER NOT NULL,
            unit TEXT NOT NULL UNIQUE, receipt TEXT NOT NULL, cgroup TEXT,
            modes_json TEXT NOT NULL, created_at TEXT NOT NULL, receipt_sha256 TEXT);
        CREATE TABLE IF NOT EXISTS events (
            job_id TEXT NOT NULL REFERENCES jobs(job_id), revision INTEGER NOT NULL,
            at TEXT NOT NULL, state TEXT NOT NULL, details_json TEXT NOT NULL,
            PRIMARY KEY(job_id,revision));
        CREATE TABLE IF NOT EXISTS recoveries (
            event_key TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(job_id),
            expected_revision INTEGER NOT NULL, actor_json TEXT NOT NULL, reason TEXT NOT NULL,
            result_json TEXT, created_at TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
            BEGIN SELECT RAISE(ABORT,'immutable_event'); END;
        CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
            BEGIN SELECT RAISE(ABORT,'immutable_event'); END;
    ''')
    return db


def transition(db, job_id, state, details=None, *, group=None, checksum=None):
    db.execute('BEGIN IMMEDIATE')
    try:
        row = db.execute('SELECT revision,state FROM jobs WHERE job_id=?', (job_id,)).fetchone()
        if row is None or row[1] in FINAL:
            raise Blocked('invalid_job_transition')
        revision = row[0] + 1
        db.execute('UPDATE jobs SET state=?,revision=?,cgroup=COALESCE(?,cgroup),receipt_sha256=COALESCE(?,receipt_sha256) WHERE job_id=?',
                   (state, revision, group, checksum, job_id))
        db.execute('INSERT INTO events VALUES(?,?,?,?,?)', (job_id, revision, stamp(), state, json.dumps(details or {})))
        db.execute('COMMIT')
        return revision
    except BaseException:
        db.execute('ROLLBACK')
        raise


def _command(args, timeout=15):
    try:
        return subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Blocked('service_manager_unavailable') from None


class SystemdBackend:
    def __init__(self):
        self.run_binary = shutil.which('systemd-run')
        self.control_binary = shutil.which('systemctl')

    def preflight(self):
        if sys.platform != 'linux' or os.geteuid() == 0:
            raise Blocked('non_root_linux_user_required')
        if not self.run_binary or not self.control_binary:
            raise Blocked('systemd_tools_missing')
        root = Path('/sys/fs/cgroup')
        if not (root / 'cgroup.controllers').is_file():
            raise Blocked('cgroup_v2_required')
        controllers = set((root / 'cgroup.controllers').read_text().split())
        if not {'cpu', 'memory', 'pids'} <= controllers:
            raise Blocked('cgroup_controllers_unavailable')
        version = _command([self.run_binary, '--version']).stdout.splitlines()[0].split()
        if len(version) < 2 or not version[1].isdigit() or int(version[1]) < 254:
            raise Blocked('systemd_254_required')
        status = _command([self.control_binary, '--user', 'is-system-running'])
        if status.stdout.strip() not in ('running', 'degraded'):
            raise Blocked('user_service_manager_unavailable')
        return dict(status='PREFLIGHT_PASS', systemd_version=version[1],
                    live_containment='NOT_TESTED', controllers=sorted(controllers))

    def start(self, unit, launch, cwd, seconds, memory_bytes, tasks, cpu_percent):
        # systemd owns the cgroup. Do NOT delegate its control to an agent process.
        command = [self.run_binary, '--user', '--quiet', '--no-ask-password', '--expand-environment=no',
            '--unit=' + unit, '--description=AfyaEvidence bounded synthetic investigation',
            '--property=Type=exec', '--property=RemainAfterExit=yes', '--property=Restart=no',
            '--property=KillMode=control-group', '--property=SendSIGKILL=yes',
            '--property=TimeoutStopSec=5s', f'--property=RuntimeMaxSec={seconds}s',
            f'--property=MemoryMax={memory_bytes}', f'--property=TasksMax={tasks}',
            f'--property=CPUQuota={cpu_percent}%', '--property=NoNewPrivileges=yes',
            '--property=Delegate=no', '--property=ProtectControlGroups=yes',
            '--property=UMask=0077', '--property=StandardOutput=null', '--property=StandardError=null',
            '--property=UnsetEnvironment=AFYA_REVIEW_TOKEN AFYA_OIDC_CLIENT_SECRET',
            '--working-directory=' + str(cwd), '--', sys.executable, '-I',
            str(Path(__file__).with_name('managed_entry.py')), str(launch)]
        if _command(command).returncode:
            raise Blocked('service_start_failed')

    def status(self, unit):
        result = _command([self.control_binary, '--user', 'show', unit,
            '--property=LoadState,ActiveState,SubState,Result,ControlGroup,MainPID,ExecMainStatus'])
        values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        if values.get('LoadState') == 'not-found':
            return values
        if result.returncode or values.get('LoadState') != 'loaded':
            raise Blocked('service_status_unavailable')
        return values

    def verify_limits(self, group, memory_bytes, tasks, cpu_percent):
        if not group or not group.startswith('/') or '..' in Path(group).parts or group == '/':
            raise Blocked('cgroup_identity_unavailable')
        directory = Path('/sys/fs/cgroup') / group.lstrip('/')
        try:
            memory = int((directory / 'memory.max').read_text().strip())
            pids = int((directory / 'pids.max').read_text().strip())
            quota, period = map(int, (directory / 'cpu.max').read_text().split())
            if not (0 < memory <= memory_bytes and 0 < pids <= tasks and
                    0 < quota * 100 <= cpu_percent * period):
                raise ValueError('limits_not_effective')
        except (OSError, ValueError):
            raise Blocked('resource_limits_not_effective') from None

    def empty(self, group):
        if not group:
            return True
        if not group.startswith('/') or '..' in Path(group).parts or group == '/':
            raise Blocked('invalid_cgroup_identity')
        path = Path('/sys/fs/cgroup') / group.lstrip('/') / 'cgroup.events'
        try:
            values = dict(line.split() for line in path.read_text().splitlines())
        except FileNotFoundError:
            return True  # A removed cgroup has no resident tasks.
        except (OSError, ValueError):
            raise Blocked('cgroup_state_unavailable') from None
        if values.get('populated') not in ('0', '1'):
            raise Blocked('cgroup_state_unavailable')
        return values['populated'] == '0'

    def stop_and_confirm(self, unit, group):
        status = self.status(unit)
        group = status.get('ControlGroup') or group
        if status.get('LoadState') != 'not-found':
            if _command([self.control_binary, '--user', 'stop', unit], timeout=15).returncode:
                raise Blocked('service_stop_failed')
        end = time.monotonic() + 10
        while time.monotonic() < end:
            current = self.status(unit)
            if current.get('ActiveState') not in ('active', 'activating', 'deactivating', 'reloading') and self.empty(group):
                return
            time.sleep(.1)
        raise Blocked('cgroup_cleanup_unconfirmed')


def validate_args(args):
    if not args or len(args) % 2 or len(args) > 48:
        raise ValueError('explicit_agent_option_values_required')
    options = {}
    for flag, value in zip(args[::2], args[1::2]):
        if flag not in AGENT_OPTIONS or flag in options or not isinstance(value, str) or not 1 <= len(value) <= 2048 or '\x00' in value:
            raise ValueError('invalid_agent_option')
        options[flag] = value
    if options.get('--data-mode') not in ('fixture', 'zetaris') or options.get('--model-provider') not in ('scripted', 'ollama') or '--snapshot' not in options:
        raise ValueError('explicit_agent_modes_required')
    return options


def receipt_result(path, modes):
    if path.is_symlink():
        return 'invalid_receipt', None
    try:
        with path.open('rb') as source:
            blob = source.read(4_000_001)
        if len(blob) > 4_000_000:
            return 'invalid_receipt', None
        data = json.loads(blob)
        brief = data.get('candidate_brief') or {}
        valid = (data.get('execution_status') == 'ready_for_review'
            and data.get('data_mode') == modes['data_mode'] and data.get('model_mode') == modes['model_mode']
            and data.get('memory_mode') == modes['memory_mode']
            and brief.get('review_status') == 'awaiting_human_review'
            and brief.get('semantic_review_required') is True and 'approval' in brief and brief['approval'] is None)
        return ('ready_for_review' if valid else 'failed'), sha256(blob).hexdigest()
    except (OSError, ValueError, TypeError, AttributeError):
        return 'missing_or_invalid_receipt', None


def run_job(root, project, args, *, backend=None, seconds=660, memory_bytes=2_147_483_648, tasks=128, cpu_percent=100, cancel=None):
    if (type(seconds) is not int or not 1 <= seconds <= 3600 or type(memory_bytes) is not int
            or not 134_217_728 <= memory_bytes <= 17_179_869_184 or type(tasks) is not int
            or not 8 <= tasks <= 512 or type(cpu_percent) is not int or not 1 <= cpu_percent <= 400):
        raise ValueError('invalid_resource_limits')
    options = validate_args(args)
    project = project.resolve(strict=True)
    if not (project / 'src/afyaevidence/agent_cli.py').is_file():
        raise ValueError('project_agent_missing')
    backend = backend or SystemdBackend()
    backend.preflight()
    root = private_state(root)
    cancel = cancel or threading.Event()
    with ownership(root), closing(database(root)) as db:
        if db.execute('SELECT 1 FROM jobs WHERE state NOT IN (?,?,?,?,?) LIMIT 1', tuple(sorted(FINAL))).fetchone():
            raise Blocked('prior_job_requires_reconciliation')
        job = 'mw_' + uuid.uuid4().hex
        unit = 'afya-' + job[3:] + '.service'
        receipt = root / (job + '.receipt.json')
        launch = root / (job + '.launch.json')
        modes = dict(data_mode=options['--data-mode'], model_mode=options['--model-provider'],
                     memory_mode=options.get('--memory', 'disabled_fixture'))
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)', (job, 'intent', 0, unit, str(receipt), None, json.dumps(modes), stamp(), None))
        db.execute('INSERT INTO events VALUES(?,?,?,?,?)', (job, 0, stamp(), 'intent', json.dumps(dict(actor='local_operator_unverified'))))
        db.execute('COMMIT')
        group = None
        outcome, checksum = 'needs_operator_reconciliation', None
        try:
            env = {k: v for k, v in os.environ.items() if k in ENV_ALLOW}
            if options['--data-mode'] == 'fixture':
                env.pop('ZETARIS_PASSWORD', None)
                env.pop('ZETARIS_USERNAME', None)
            env.update(PYTHONPATH=str(project / 'src'), PYTHONUNBUFFERED='1')
            fd = os.open(launch, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as stream:
                json.dump(dict(argv=[sys.executable, '-m', 'afyaevidence.agent_cli', *args, '--output', str(receipt)], env=env), stream)
                stream.flush()
                os.fsync(stream.fileno())
            backend.start(unit, launch, project, seconds, memory_bytes, tasks, cpu_percent)
            status = backend.status(unit)
            group = status.get('ControlGroup') or None
            backend.verify_limits(group, memory_bytes, tasks, cpu_percent)
            transition(db, job, 'running', dict(unit=unit, main_pid=status.get('MainPID')), group=group)
            deadline = time.monotonic() + seconds + 10
            while True:
                status = backend.status(unit)
                if cancel.is_set():
                    outcome = 'cancelled'
                    break
                if time.monotonic() >= deadline:
                    outcome = 'failed'
                    break
                if status.get('LoadState') == 'not-found':
                    raise Blocked('unit_disappeared_before_completion')
                if status.get('SubState') in ('exited', 'dead', 'failed') or status.get('ActiveState') in ('inactive', 'failed'):
                    receipt_status, checksum = receipt_result(receipt, modes)
                    outcome = 'ready_for_review' if status.get('Result') == 'success' and status.get('ExecMainStatus') == '0' and receipt_status == 'ready_for_review' else 'failed'
                    break
                time.sleep(.1)
            backend.stop_and_confirm(unit, group)
            transition(db, job, outcome, dict(result=status.get('Result'), service_exit=status.get('ExecMainStatus')),
                       group=group, checksum=checksum)
        except BaseException as exc:
            # A lost systemd response or unconfirmed cleanup MUST keep admission blocked.
            try:
                backend.stop_and_confirm(unit, group)
            except Exception:
                pass
            transition(db, job, 'needs_operator_reconciliation', dict(error='worker_control_interrupted'), group=group)
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
        finally:
            launch.unlink(missing_ok=True)
        return job_status(db, job)


def job_status(db, job):
    row = db.execute('SELECT job_id,state,revision,unit,cgroup,receipt_sha256 FROM jobs WHERE job_id=?', (job,)).fetchone()
    if row is None:
        raise ValueError('unknown_job')
    result = dict(zip(('job_id', 'state', 'revision', 'unit', 'cgroup', 'receipt_sha256'), row))
    result['events'] = [dict(revision=e[0], at=e[1], state=e[2], details=json.loads(e[3]))
                        for e in db.execute('SELECT revision,at,state,details_json FROM events WHERE job_id=? ORDER BY revision', (job,))]
    return result


def audit(root):
    if not root.exists():
        return dict(state='NO_MANAGED_STATE', jobs=[])
    root = private_state(root)
    if not (root / 'managed.sqlite3').is_file():
        return dict(state='NO_MANAGED_JOBS', jobs=[])
    try:
        db = sqlite3.connect((root / 'managed.sqlite3').as_uri() + '?mode=ro', uri=True)
    except sqlite3.Error:
        raise Blocked('job_audit_unavailable') from None
    with closing(db):
        jobs = [job_status(db, row[0]) for row in db.execute('SELECT job_id FROM jobs ORDER BY created_at')]
    return dict(state='RECONCILIATION_REQUIRED' if any(j['state'] not in FINAL for j in jobs) else 'FINALISED', jobs=jobs)


def reconcile(root, job, *, principal: Principal, expected_revision, event_key, reason, backend=None):
    principal.require('recover')
    if not isinstance(job, str) or not JOB_ID.fullmatch(job) or not isinstance(event_key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', event_key):
        raise ValueError('invalid_identifier')
    if type(expected_revision) is not int or expected_revision < 0 or not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 2000:
        raise ValueError('invalid_recovery_request')
    root = private_state(root)
    backend = backend or SystemdBackend()
    backend.preflight()
    with ownership(root), closing(database(root)) as db:
        prior = db.execute('SELECT job_id,expected_revision,actor_json,reason,result_json FROM recoveries WHERE event_key=?', (event_key,)).fetchone()
        actor = json.dumps(principal.public(), sort_keys=True)
        if prior:
            if prior[:4] != (job, expected_revision, actor, reason.strip()):
                raise ValueError('idempotency_conflict')
            if prior[4]:
                return json.loads(prior[4])
            completed = job_status(db, job)
            final_event = completed['events'][-1]
            if completed['state'] in FINAL and final_event['details'].get('event_key') == event_key:
                # Recover a committed final event after a lost acknowledgement; no stop/replay.
                db.execute('UPDATE recoveries SET result_json=? WHERE event_key=?', (json.dumps(completed), event_key))
                return completed
            raise Blocked('recovery_interrupted_use_new_event_key')
        state = job_status(db, job)
        if state['state'] in FINAL or state['revision'] != expected_revision:
            raise ValueError('revision_conflict')
        # Journal the authenticated operator intent BEFORE external stop requests.
        db.execute('INSERT INTO recoveries VALUES(?,?,?,?,?,?,?)',
                   (event_key, job, expected_revision, actor, reason.strip(), None, stamp()))
        transition(db, job, 'reconciling', dict(event_key=event_key, actor=principal.public(), reason=reason.strip()))
        try:
            backend.stop_and_confirm(state['unit'], state['cgroup'])
            (root / (job + '.launch.json')).unlink(missing_ok=True)
            row = db.execute('SELECT receipt,modes_json FROM jobs WHERE job_id=?', (job,)).fetchone()
            result, checksum = receipt_result(Path(row[0]), json.loads(row[1]))
            final = 'reconciled_ready_for_review' if result == 'ready_for_review' else 'reconciled_failed'
            transition(db, job, final, dict(event_key=event_key, actor=principal.public(), reason=reason.strip()), checksum=checksum)
            reply = job_status(db, job)
            db.execute('UPDATE recoveries SET result_json=? WHERE event_key=?', (json.dumps(reply), event_key))
            return reply
        except BaseException:
            transition(db, job, 'needs_operator_reconciliation', dict(event_key=event_key, error='recovery_cleanup_unconfirmed'))
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'audit', 'run'))
    parser.add_argument('--state-dir', type=Path, default=Path.home() / '.local/state/afyaevidence-managed')
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--timeout', type=int, default=660)
    args, remaining = parser.parse_known_args(argv)
    if remaining[:1] == ['--']:
        remaining = remaining[1:]
    try:
        if args.action == 'preflight':
            result = SystemdBackend().preflight()
        elif args.action == 'audit':
            result = audit(args.state_dir)
        else:
            options = validate_args(remaining)
            if options.get('--data-mode') == 'zetaris' and not os.environ.get('ZETARIS_PASSWORD'):
                if not sys.stdin.isatty():
                    raise Blocked('private_jdbc_credential_required')
                import getpass
                os.environ['ZETARIS_PASSWORD'] = getpass.getpass('Zetaris password (private): ')
            event = threading.Event()
            original = {s: signal.signal(s, lambda *_: event.set()) for s in (signal.SIGTERM, signal.SIGINT)}
            try:
                result = run_job(args.state_dir, args.project, remaining, seconds=args.timeout, cancel=event)
            finally:
                for sig, handler in original.items():
                    signal.signal(sig, handler)
        print(json.dumps(result, indent=2))
        return 0 if result.get('state') not in {'failed', 'cancelled', 'needs_operator_reconciliation', 'RECONCILIATION_REQUIRED'} else 1
    except (Blocked, ValueError) as exc:
        print('MANAGED_WORKER=BLOCKED\nREASON=' + str(exc))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
