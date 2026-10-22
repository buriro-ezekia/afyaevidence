"""Single-slot supervised agent launcher with durable status and no automatic retry.

Runs the existing CLI as a child. Never invokes shell, changes sources or
substitutes fixture data when the requested live provider fails.
"""
from __future__ import annotations

import argparse
import fcntl
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid


def write_exclusive(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())


def _subreaper(enabled=None):
    # Ubuntu/Linux: adopt and reap orphaned members of our worker process group.
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    if libc.prctl(37, ctypes.byref(previous), 0, 0, 0) != 0:
        raise OSError("subreaper_unavailable")
    if enabled is not None and libc.prctl(36, int(enabled), 0, 0, 0) != 0:
        raise OSError("subreaper_unavailable")
    return previous.value


def _signal_group(pgid, sig):
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


def _group_exists(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


def _reap_group(pgid):
    while True:
        try:
            pid, _ = os.waitpid(-pgid, os.WNOHANG)
            if pid == 0:
                return
        except ChildProcessError:
            return


def terminate_group(proc):
    # Always clean the group, even if its leader exited before descendants did.
    _signal_group(proc.pid, signal.SIGTERM)
    grace = time.monotonic() + 5
    while time.monotonic() < grace:
        proc.poll()
        if proc.returncode is not None:
            _reap_group(proc.pid)
        if not _group_exists(proc.pid):
            proc.wait()
            return
        time.sleep(.05)
    _signal_group(proc.pid, signal.SIGKILL)
    proc.wait()
    # Do not publish a final event or release ownership while a child is alive.
    # A stuck uninterruptible process needs operator intervention, not a replay.
    while True:
        _reap_group(proc.pid)
        if not _group_exists(proc.pid):
            return
        time.sleep(.05)


def supervise(argv, *, state_dir: Path, timeout: int = 660):
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise ValueError("invalid supervisor timeout")
    if not argv or argv[0] != sys.executable:
        raise ValueError("expected current python executable")
    if argv[1:3] != ["-m", "afyaevidence.agent_cli"]:
        raise ValueError("only bounded agent module is permitted")
    if "--output" not in argv or argv.count("--output") != 1 or argv[-1] == "--output":
        raise ValueError("explicit output required")
    output = Path(argv[argv.index("--output") + 1])
    if output.exists():
        raise ValueError("receipt path exists")
    state_dir.mkdir(parents=True, exist_ok=True)
    requested_signal = None
    def interrupt(signum, frame):
        nonlocal requested_signal
        requested_signal = signum
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    lock = None
    previous_subreaper = None
    try:
        for sig in handlers:
            signal.signal(sig, interrupt)
        lock = (state_dir / ".worker.lock").open("a+")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return dict(job_id=None, state="busy", receipt_execution_status=None)
        from .job_audit import audit_jobs
        if any(item["state"] != "finalised" for item in audit_jobs(state_dir)):
            return dict(job_id=None, state="needs_operator_reconciliation", receipt_execution_status=None)
        # Check again under ownership; never overwrite a receipt from another run.
        if output.exists():
            raise ValueError("receipt path exists")
        previous_subreaper = _subreaper(True)
        job_id = "job_" + uuid.uuid4().hex
        started = datetime.now(timezone.utc).isoformat()
        write_exclusive(state_dir / (job_id + ".json"), dict(
            job_id=job_id, state="running", started_at=started,
            receipt=str(output), deadline_seconds=timeout))
        proc, outcome, rc = None, "interrupted", None
        try:
            if requested_signal is None:
                proc = subprocess.Popen(argv, stdin=None, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True, pass_fds=(lock.fileno(),),
                    env={key: value for key, value in os.environ.items() if key != "AFYA_REVIEW_TOKEN"})
                deadline = time.monotonic() + timeout
                while requested_signal is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        outcome = "timed_out"
                        break
                    try:
                        rc = proc.wait(timeout=min(.1, remaining))
                        outcome = "finished" if rc == 0 and output.is_file() else "failed"
                        break
                    except subprocess.TimeoutExpired:
                        continue
            if requested_signal is not None:
                outcome = "cancelled" if requested_signal == signal.SIGINT else "interrupted"
        except KeyboardInterrupt:
            outcome = "cancelled"
        except Exception:
            outcome = "failed"
        finally:
            if proc is not None:
                terminate_group(proc)
                rc = proc.returncode
            if requested_signal is not None:
                outcome = "cancelled" if requested_signal == signal.SIGINT else "interrupted"
            receipt_status = None
            if output.is_file():
                try:
                    with output.open("rb") as stream:
                        blob = stream.read(4_000_001)
                    if len(blob) > 4_000_000:
                        raise ValueError("oversized receipt")
                    doc = json.loads(blob)
                    receipt_status = doc.get("execution_status") if isinstance(doc, dict) else "unreadable"
                except (OSError, ValueError):
                    receipt_status = "unreadable"
            updated = dict(job_id=job_id, state=outcome, started_at=started,
                ended_at=datetime.now(timezone.utc).isoformat(), receipt=str(output),
                receipt_execution_status=receipt_status, returncode=rc,
                termination_signal=requested_signal, cleanup_complete=True)
            write_exclusive(state_dir / (job_id + ".final.json"), updated)
        return updated
    finally:
        # Closing (not LOCK_UN) keeps inherited ownership alive if the supervisor
        # is killed. Missing final events additionally block replacement/replay.
        if lock is not None:
            lock.close()
        if previous_subreaper is not None:
            _subreaper(previous_subreaper)
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state-dir",type=Path,default=Path("runtime/jobs"))
    p.add_argument("--timeout",type=int,default=660)
    p.add_argument("agent_args",nargs=argparse.REMAINDER)
    args=p.parse_args(argv)
    params=args.agent_args
    if params and params[0]=="--":
        params=params[1:]
    if not params:
        p.error("agent arguments required after --")
    result=supervise([sys.executable,"-m","afyaevidence.agent_cli",*params],
                     state_dir=args.state_dir,timeout=args.timeout)
    print("SUPERVISED_STATE="+result["state"])
    print("RECEIPT_STATUS="+str(result["receipt_execution_status"]))
    return 0 if result["state"]=="finished" and result["receipt_execution_status"]=="ready_for_review" else 1


if __name__=="__main__":
    raise SystemExit(main())
