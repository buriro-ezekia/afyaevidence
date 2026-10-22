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


def supervise(argv, *, state_dir: Path, timeout: int = 660):
    if not 1 <= timeout <= 3600:
        raise ValueError("invalid supervisor timeout")
    if not argv or argv[0] != sys.executable:
        raise ValueError("expected current python executable")
    if argv[1:3] != ["-m", "afyaevidence.agent_cli"]:
        raise ValueError("only bounded agent module is permitted")
    if "--output" not in argv or argv.count("--output") != 1:
        raise ValueError("explicit output required")
    output = Path(argv[argv.index("--output") + 1])
    if output.exists():
        raise ValueError("receipt path exists")
    run_id = "job_" + uuid.uuid4().hex
    start = datetime.now(timezone.utc).isoformat()
    status_path = state_dir / (run_id + ".json")
    state_dir.mkdir(parents=True, exist_ok=True)
    # Log only statuses and paths: argv and env may contain sensitive values.
    write_exclusive(status_path, dict(job_id=run_id, state="running", started_at=start,
                                     receipt=str(output), deadline_seconds=timeout))
    lock = (state_dir / ".worker.lock").open("a+")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        write_exclusive(state_dir / (run_id + ".final.json"),
                        dict(job_id=run_id,state="busy",started_at=start,
                             ended_at=datetime.now(timezone.utc).isoformat(),
                             receipt=str(output),receipt_execution_status=None))
        return dict(job_id=run_id,state="busy",receipt_execution_status=None)
    proc = None
    outcome = "interrupted"
    try:
        proc = subprocess.Popen(argv, stdin=None, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            rc = proc.wait(timeout=timeout)
            outcome = "finished" if rc == 0 and output.is_file() else "failed"
        except subprocess.TimeoutExpired:
            outcome = "timed_out"
        except KeyboardInterrupt:
            outcome = "cancelled"
            raise
    finally:
        if proc is not None and proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        receipt_status = None
        if output.is_file():
            try:
                receipt_status = json.loads(output.read_text(encoding="utf-8")).get("execution_status")
            except (OSError, ValueError):
                receipt_status = "unreadable"
        updated = dict(job_id=run_id, state=outcome, started_at=start,
                       ended_at=datetime.now(timezone.utc).isoformat(),
                       receipt=str(output), receipt_execution_status=receipt_status)
        # Immutable event, never overwrite initial job record.
        write_exclusive(state_dir / (run_id + ".final.json"), updated)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()
    return updated


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
