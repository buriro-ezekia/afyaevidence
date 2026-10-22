"""Local-only authenticated review API; no agent tools or source mutation.

Run with python -m afyaevidence.review_server after setting
AFYA_REVIEW_TOKEN and AFYA_REVIEW_DB. Bind remains loopback-only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, receipt_path TEXT NOT NULL UNIQUE,
  receipt_sha256 TEXT NOT NULL, snapshot_id TEXT NOT NULL,
  candidate_json TEXT NOT NULL, created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0, disposition TEXT
);
CREATE TABLE IF NOT EXISTS reviews (
  run_id TEXT NOT NULL, revision INTEGER NOT NULL,
  event_key TEXT NOT NULL, reviewer TEXT NOT NULL,
  disposition TEXT NOT NULL, reason TEXT NOT NULL, at TEXT NOT NULL,
  PRIMARY KEY(run_id,revision), UNIQUE(run_id,event_key),
  FOREIGN KEY(run_id) REFERENCES runs(run_id)
);
"""
DECISIONS = frozenset(("accept", "request_more_evidence", "reject"))
ID = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")


def connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15, isolation_level=None)
    db.execute("PRAGMA busy_timeout=15000")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(SCHEMA)
    return db


def utc():
    return datetime.now(timezone.utc).isoformat()


def validate_receipt(blob: bytes):
    if len(blob) > 4_000_000:
        raise ValueError("receipt_too_large")
    doc = json.loads(blob)
    if not isinstance(doc, dict) or doc.get("execution_status") != "ready_for_review":
        raise ValueError("receipt_not_ready")
    brief = doc.get("candidate_brief")
    if not isinstance(brief, dict) or brief.get("review_status") != "awaiting_human_review":
        raise ValueError("review_status_invalid")
    if brief.get("semantic_review_required") is not True or brief.get("approval") is not None:
        raise ValueError("human_boundary_invalid")
    snapshot = doc.get("snapshot_id") or doc.get("evidence_bundle", {}).get("snapshot_id")
    if not isinstance(snapshot, str) or not snapshot:
        raise ValueError("snapshot_missing")
    return doc, brief, snapshot


def import_receipt(db, receipt: Path, *, root: Path):
    root = root.resolve()
    path = receipt.resolve(strict=True)
    if not path.is_relative_to(root) or path.suffix != ".json":
        raise ValueError("receipt_outside_runtime")
    blob = path.read_bytes()
    doc, brief, snapshot = validate_receipt(blob)
    checksum = sha256(blob).hexdigest()
    run_id = doc.get("run_id")
    if not isinstance(run_id, str) or not ID.fullmatch(run_id):
        run_id = "run_" + checksum[:24]
    candidate = json.dumps(brief, sort_keys=True, separators=(",", ":"))
    db.execute("BEGIN IMMEDIATE")
    try:
        existing = db.execute("SELECT receipt_sha256 FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if existing and existing[0] != checksum:
            raise ValueError("immutable_run_conflict")
        db.execute("""INSERT OR IGNORE INTO runs
            (run_id,receipt_path,receipt_sha256,snapshot_id,candidate_json,created_at)
            VALUES(?,?,?,?,?,?)""", (run_id,str(path),checksum,snapshot,candidate,utc()))
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    return run_id


def review(db, *, run_id, expected_revision, event_key, reviewer, disposition, reason):
    if not isinstance(run_id, str) or not ID.fullmatch(run_id):
        raise ValueError("invalid_run")
    if not isinstance(event_key, str) or not ID.fullmatch(event_key):
        raise ValueError("invalid_event_key")
    if not isinstance(reviewer, str) or not 1 <= len(reviewer) <= 120:
        raise ValueError("invalid_reviewer")
    if disposition not in DECISIONS:
        raise ValueError("invalid_disposition")
    if not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 2000:
        raise ValueError("reason_required")
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("invalid_revision")
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute("SELECT revision,disposition FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise ValueError("unknown_run")
        prior = db.execute("SELECT revision,disposition,reason FROM reviews WHERE run_id=? AND event_key=?",
                           (run_id,event_key)).fetchone()
        if prior:
            if prior[1] != disposition or prior[2] != reason.strip():
                raise ValueError("idempotency_conflict")
            result = {"run_id":run_id,"revision":prior[0],"disposition":prior[1],"replayed":True}
        else:
            if row[1] is not None:
                raise ValueError("already_reviewed")
            if row[0] != expected_revision:
                raise ValueError("revision_conflict")
            next_revision = expected_revision + 1
            db.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?,?)",
                       (run_id,next_revision,event_key,reviewer,disposition,reason.strip(),utc()))
            db.execute("UPDATE runs SET revision=?,disposition=? WHERE run_id=? AND revision=?",
                       (next_revision,disposition,run_id,expected_revision))
            result = {"run_id":run_id,"revision":next_revision,"disposition":disposition,"replayed":False}
        db.execute("COMMIT")
        return result
    except BaseException:
        db.execute("ROLLBACK")
        raise


def get_run(db, run_id):
    row = db.execute("SELECT run_id,snapshot_id,receipt_sha256,candidate_json,revision,disposition "
                     "FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not row:
        raise ValueError("unknown_run")
    return dict(run_id=row[0],snapshot_id=row[1],receipt_sha256=row[2],
                candidate=json.loads(row[3]),revision=row[4],disposition=row[5])


PAGE = """<!doctype html><html lang="en"><meta charset="utf-8">
<title>AfyaEvidence local review</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font:16px system-ui;max-width:850px;margin:3rem auto;padding:1rem}
textarea,input,select,button{display:block;margin:.7rem 0;padding:.6rem;max-width:100%;width:100%;box-sizing:border-box}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef2f6;padding:1rem}
small{color:#555}</style>
<h1>AfyaEvidence — human review</h1>
<p>Local evidence review only. This does not approve a clinical decision or change source data.</p>
<label>Review bearer token (held in this tab only)<input type="password" id="token"></label>
<label>Run ID<input id="run"></label><button onclick="load()">Load candidate</button>
<pre id="candidate">No run loaded.</pre>
<label>Disposition<select id="decision"><option value="accept">Accept for review record</option>
<option value="request_more_evidence">Request more evidence</option><option value="reject">Reject</option></select></label>
<label>Reason (minimum 10 characters)<textarea id="reason"></textarea></label>
<button onclick="submitReview()">Record disposition</button><pre id="status"></pre>
<small>Token is not stored or transmitted except in requests to this loopback service.</small>
<script>
let revision=null;
async function api(path,method='GET',body=null){
const response=await fetch(path,{method,headers:{'Authorization':'Bearer '+document.getElementById('token').value,
'Content-Type':'application/json'},body:body?JSON.stringify(body):null});
const result=await response.json();if(!response.ok)throw Error(result.error||response.status);return result;
}
async function load(){try{
const r=await api('/api/runs/'+encodeURIComponent(document.getElementById('run').value));
revision=r.revision;document.getElementById('candidate').textContent=JSON.stringify(r,null,2);
}catch(e){document.getElementById('status').textContent=e.message}}
async function submitReview(){try{
if(revision===null)throw Error('Load a candidate first');
const r=await api('/api/runs/'+encodeURIComponent(document.getElementById('run').value)+'/reviews','POST',
{expected_revision:revision,event_key:crypto.randomUUID().replaceAll('-',''),
disposition:document.getElementById('decision').value,reason:document.getElementById('reason').value});
document.getElementById('status').textContent=JSON.stringify(r);await load();
}catch(e){document.getElementById('status').textContent=e.message}}
</script></html>"""


def handler_factory(db_path: Path, token: str):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, obj):
            blob = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

        def authorised(self):
            supplied = self.headers.get("Authorization", "")
            return compare_digest(supplied.encode(), ("Bearer " + token).encode())

        def do_GET(self):
            route = urlsplit(self.path).path
            if route == "/":
                blob = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type","text/html; charset=utf-8")
                self.send_header("Cache-Control","no-store")
                self.send_header("Content-Security-Policy","default-src 'self' 'unsafe-inline'")
                self.send_header("Content-Length",str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)
                return
            if not self.authorised():
                self.reply(401,{"error":"unauthorised"});return
            match = re.fullmatch(r"/api/runs/([a-zA-Z0-9_-]{1,100})",route)
            if not match:
                self.reply(404,{"error":"not_found"});return
            with connect(db_path) as db:
                try:self.reply(200,get_run(db,match[1]))
                except ValueError as exc:self.reply(404,{"error":str(exc)})

        def do_POST(self):
            if not self.authorised():
                self.reply(401,{"error":"unauthorised"});return
            match = re.fullmatch(r"/api/runs/([a-zA-Z0-9_-]{1,100})/reviews",urlsplit(self.path).path)
            if not match:
                self.reply(404,{"error":"not_found"});return
            try:
                length = int(self.headers.get("Content-Length","0"))
                if not 0 < length <= 4096:raise ValueError("invalid_body_size")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload,dict) or set(payload) != {"expected_revision","event_key","disposition","reason"}:
                    raise ValueError("invalid_fields")
                with connect(db_path) as db:
                    outcome=review(db,run_id=match[1],reviewer="local_operator",
                                   **payload)
                self.reply(200,outcome)
            except (ValueError,TypeError,sqlite3.Error) as exc:
                self.reply(409,{"error":str(exc)})
    return Handler


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",type=Path,default=Path(os.getenv("AFYA_REVIEW_DB","runtime/reviews.sqlite3")))
    p.add_argument("--runtime-root",type=Path,default=Path("runtime"))
    p.add_argument("--import-receipt",type=Path)
    p.add_argument("--port",type=int,default=8010)
    args=p.parse_args()
    if args.import_receipt:
        with connect(args.db) as db:
            print("IMPORTED_RUN="+import_receipt(db,args.import_receipt,root=args.runtime_root))
        return
    token=os.getenv("AFYA_REVIEW_TOKEN","")
    if len(token)<32:raise SystemExit("AFYA_REVIEW_TOKEN must be at least 32 characters")
    server=ThreadingHTTPServer(("127.0.0.1",args.port),handler_factory(args.db,token))
    print(f"REVIEW_UI=http://127.0.0.1:{args.port}/",flush=True)
    server.serve_forever()


if __name__=="__main__":main()
