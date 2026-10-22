"""Conservative restart audit of supervised job event files.

Never resumes, retries or changes a running investigation.
"""
import argparse
import json
from pathlib import Path

def audit_jobs(state_dir: Path):
    results=[]
    if not state_dir.exists():
        return results
    for path in sorted(state_dir.glob("job_*.json")):
        if path.name.endswith(".final.json"):
            continue
        job_id=path.stem
        final=state_dir/(job_id+".final.json")
        try:
            initial=json.loads(path.read_text(encoding="utf-8"))
            if initial.get("job_id")!=job_id or initial.get("state")!="running":
                state="invalid_start_record"
            elif final.exists():
                completed=json.loads(final.read_text(encoding="utf-8"))
                state="finalised" if completed.get("job_id")==job_id else "invalid_final_record"
            else:
                state="needs_operator_reconciliation"
        except (OSError,ValueError):
            state="corrupt_event_record"
        results.append(dict(job_id=job_id,state=state))
    return results

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir",type=Path,default=Path("runtime/jobs"))
    args=parser.parse_args()
    result=audit_jobs(args.state_dir)
    print(json.dumps(result,indent=2))
    return 1 if any(item["state"]!="finalised" for item in result) else 0

if __name__=="__main__":
    raise SystemExit(main())
