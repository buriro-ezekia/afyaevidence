#!/usr/bin/env python3
"""Reject a runtime wheel containing evaluator code, data or local credentials."""
import argparse
import json
from pathlib import Path
import zipfile
import subprocess
import sys
import tempfile


def check(path):
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        allowed = {"afyaevidence/" + name for name in ("__init__.py", "contracts.py", "snapshot.py", "jdbc.py", "analysis.py", "cli.py", "memory.py", "agent.py", "model.py", "agent_cli.py", "review_server.py", "review_page.py", "supervisor.py", "job_audit.py", "identity_auth.py", "identity_store.py", "identity_page.py", "identity_review_server.py", "managed_entry.py", "managed_worker.py")}
        required_meta = {"METADATA", "WHEEL", "top_level.txt", "RECORD"}
        for name in names:
            parts = name.split("/")
            if name in allowed:
                continue
            if (len(parts) == 2 and parts[0].startswith("afyaevidence-") and
                parts[0].endswith(".dist-info") and parts[1] in required_meta):
                continue
            raise ValueError(f"Unexpected runtime member: {name}")
        if not allowed <= names:
            raise ValueError("Runtime contract package missing")


def smoke(path, snapshot):
    code = ("import sys; sys.path.insert(0, sys.argv[1]); "
            "from afyaevidence.cli import main; "
            "result=main(['--mode','fixture','--snapshot',sys.argv[2]]); "
            "assert not any(n == 'evals' or n.startswith('evals.') for n in sys.modules); "
            "raise SystemExit(result)")
    with tempfile.TemporaryDirectory() as temp:
        result = subprocess.run([sys.executable, "-I", "-c", code, str(path.resolve()), str(snapshot.resolve())],
                                cwd=temp, capture_output=True, text=True, timeout=30)
    if result.returncode != 0 or "LIVE_ZETARIS=NOT_RUN" not in result.stdout:
        raise ValueError("Isolated wheel execution failed")
    agent_code = ("import sys; sys.path.insert(0, sys.argv[1]); "
                  "from afyaevidence.agent_cli import main; "
                  "result=main(['--data-mode','fixture','--model-provider','scripted',"
                  "'--snapshot',sys.argv[2],'--output',sys.argv[3],'--execution-profile',sys.argv[4]]); "
                  "assert not any(n == 'evals' or n.startswith('evals.') for n in sys.modules); "
                  "raise SystemExit(result)")
    for profile in ('standard','cpu'):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'agent.json'
            result = subprocess.run([sys.executable, "-I", "-c", agent_code, str(path.resolve()),
                                     str(snapshot.resolve()),str(output),profile],
                                    cwd=temp,capture_output=True,text=True,timeout=30)
            if result.returncode != 0 or "LIVE_MODEL=NOT_RUN" not in result.stdout or "AGENT_EXECUTION=PASS" not in result.stdout:
                raise ValueError("Isolated scripted-agent wheel execution failed: "+profile)
            receipt=json.loads(output.read_text(encoding='utf-8'))
            brief=receipt['candidate_brief']
            if (receipt['execution_profile']!=profile or receipt['model_mode']!='scripted' or
                receipt['review_status']!='awaiting_human_review' or not brief['semantic_review_required'] or
                brief['approval'] is not None or (profile=='cpu' and receipt['model_calls']!=2)):
                raise ValueError("Isolated scripted-agent receipt contract failed: "+profile)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--smoke-snapshot", type=Path, help="Run packaged fixture CLI in an isolated process")
    args = parser.parse_args()
    try:
        check(args.wheel)
        if args.smoke_snapshot:
            smoke(args.wheel, args.smoke_snapshot)
    except (ValueError, OSError, zipfile.BadZipFile, subprocess.TimeoutExpired) as exc:
        print(f"RUNTIME_PACKAGE=FAIL: {exc}")
        return 1
    print("RUNTIME_PACKAGE=PASS\nEVALUATOR_KEYS_IN_WHEEL=NO\nSOURCE_DATA_IN_WHEEL=NO")
    if args.smoke_snapshot:
        print("ISOLATED_RUNTIME_WHEEL=PASS\nISOLATED_SCRIPTED_PROFILES=standard,cpu\nLIVE_MODEL=NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
