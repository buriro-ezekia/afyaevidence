"""Local-only authenticated review API; no agent tools or source mutation.

Run with python -m afyaevidence.review_server after setting
AFYA_REVIEW_TOKEN and AFYA_REVIEW_DB. Bind remains loopback-only.
"""
from __future__ import annotations

from contextlib import closing
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
from .review_page import PAGE

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, receipt_path TEXT NOT NULL UNIQUE,
  receipt_sha256 TEXT NOT NULL, snapshot_id TEXT NOT NULL,
  candidate_json TEXT NOT NULL, evidence_json TEXT NOT NULL, created_at TEXT NOT NULL,
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
SCHEMA_VERSION = 2
# 2,000 non-BMP characters can occupy 24,000 bytes as JSON surrogate escapes.
MAX_REVIEW_BODY = 32_768
EXECUTION_FIELDS = (
    "schema_version", "prompt_version", "execution_status", "failure_reason",
    "data_mode", "model_mode", "model", "memory_mode", "execution_profile",
    "model_calls", "tool_calls", "repairs", "memory_reads", "memory_pending_sync",
    "memory_as_of_utc", "model_call_limit", "model_timeout_seconds", "deadline_seconds",
    "brief_reserve_seconds", "verification", "verification_status", "verification_results",
    "live_model", "live_zetaris", "live_hmem",
    "LIVE_MODEL", "LIVE_ZETARIS", "LIVE_HMEM",
)


def strict_json(blob):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result
    try:
        return json.loads(blob, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid_json")))
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("invalid_json") from None


def execution_metadata(doc):
    # Never infer execution from the analysis bundle's not_run placeholders.
    return {key: doc.get(key) for key in EXECUTION_FIELDS}


def migrate(db):
    """Transactional v0/v1 -> v2 upgrade; never rewrite evidence or dispositions."""
    db.execute("BEGIN IMMEDIATE")
    try:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise ValueError("unsupported_review_schema")
        if version < 2:
            columns = {row[1] for row in db.execute("PRAGMA table_info(runs)")}
            if "execution_json" not in columns:
                db.execute("ALTER TABLE runs ADD COLUMN execution_json TEXT")
                db.execute("ALTER TABLE runs ADD COLUMN provenance_status TEXT NOT NULL DEFAULT 'legacy_unavailable'")
            for run_id, filename, checksum, candidate, evidence, snapshot in db.execute(
                    "SELECT run_id,receipt_path,receipt_sha256,candidate_json,evidence_json,snapshot_id FROM runs").fetchall():
                status, metadata = "legacy_unavailable", None
                try:
                    with Path(filename).open("rb") as stream:
                        blob = stream.read(4_000_001)
                    if sha256(blob).hexdigest() != checksum:
                        status = "legacy_hash_mismatch"
                    else:
                        doc, brief, found_snapshot = validate_receipt(blob)
                        found_id = receipt_run_id(doc, checksum)
                        if (found_id != run_id or found_snapshot != snapshot or
                                brief != json.loads(candidate) or doc["evidence_bundle"] != json.loads(evidence)):
                            status = "legacy_content_mismatch"
                        else:
                            metadata, status = execution_metadata(doc), "receipt_top_level"
                except (OSError, ValueError, TypeError, KeyError):
                    pass
                db.execute("UPDATE runs SET execution_json=?,provenance_status=? WHERE run_id=?",
                           (None if metadata is None else json.dumps(metadata), status, run_id))
            db.execute("PRAGMA user_version=2")
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


ID = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")


def connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15, isolation_level=None)
    db.execute("PRAGMA busy_timeout=15000")
    db.execute("PRAGMA foreign_keys=ON")
    try:
        db.executescript(SCHEMA)
        migrate(db)
        return db
    except BaseException:
        db.close()
        raise


def utc():
    return datetime.now(timezone.utc).isoformat()


def validate_receipt(blob: bytes):
    if len(blob) > 4_000_000:
        raise ValueError("receipt_too_large")
    doc = strict_json(blob)
    if not isinstance(doc, dict) or doc.get("execution_status") != "ready_for_review":
        raise ValueError("receipt_not_ready")
    brief = doc.get("candidate_brief")
    if not isinstance(brief, dict) or brief.get("review_status") != "awaiting_human_review":
        raise ValueError("review_status_invalid")
    if brief.get("semantic_review_required") is not True or brief.get("approval") is not None:
        raise ValueError("human_boundary_invalid")
    evidence = doc.get("evidence_bundle")
    if not isinstance(evidence, dict):
        raise ValueError("evidence_missing")
    if "approval" not in brief:
        raise ValueError("human_boundary_invalid")
    snapshot = doc.get("snapshot_id") or evidence.get("snapshot_id")
    if evidence.get("snapshot_id") != snapshot:
        raise ValueError("snapshot_mismatch")
    if not isinstance(snapshot, str) or not snapshot:
        raise ValueError("snapshot_missing")
    return doc, brief, snapshot


def receipt_run_id(doc, checksum):
    run_id = doc.get("run_id")
    return run_id if isinstance(run_id, str) and ID.fullmatch(run_id) else "run_" + checksum[:24]


def import_receipt(db, receipt: Path, *, root: Path):
    root = root.resolve()
    path = receipt.resolve(strict=True)
    if not path.is_relative_to(root) or path.suffix != ".json":
        raise ValueError("receipt_outside_runtime")
    with path.open("rb") as stream:
        blob = stream.read(4_000_001)
    doc, brief, snapshot = validate_receipt(blob)
    checksum = sha256(blob).hexdigest()
    run_id = receipt_run_id(doc, checksum)
    candidate = json.dumps(brief, sort_keys=True, separators=(",", ":"))
    evidence = json.dumps(doc["evidence_bundle"], sort_keys=True, separators=(",", ":"))
    db.execute("BEGIN IMMEDIATE")
    try:
        existing = db.execute("SELECT receipt_path,receipt_sha256 FROM runs WHERE run_id=?", (run_id,)).fetchone()
        by_path = db.execute("SELECT run_id,receipt_sha256 FROM runs WHERE receipt_path=?", (str(path),)).fetchone()
        if existing and existing != (str(path), checksum):
            raise ValueError("immutable_run_conflict")
        if by_path and by_path != (run_id, checksum):
            raise ValueError("immutable_path_conflict")
        metadata = json.dumps(execution_metadata(doc), sort_keys=True, separators=(",", ":"))
        if existing:
            stored = db.execute("SELECT snapshot_id,candidate_json,evidence_json FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if (stored[0] != snapshot or json.loads(stored[1]) != brief or
                    json.loads(stored[2]) != doc["evidence_bundle"]):
                raise ValueError("immutable_content_conflict")
            # Explicit re-import can recover unavailable legacy provenance only
            # from the exact original bytes and original identity/path binding.
            db.execute("UPDATE runs SET execution_json=?,provenance_status='receipt_top_level' "
                       "WHERE run_id=? AND execution_json IS NULL", (metadata, run_id))
        else:
            db.execute("""INSERT INTO runs
                (run_id,receipt_path,receipt_sha256,snapshot_id,candidate_json,evidence_json,created_at,
                 execution_json,provenance_status) VALUES(?,?,?,?,?,?,?,?,?)""",
                (run_id,str(path),checksum,snapshot,candidate,evidence,utc(),metadata,"receipt_top_level"))
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
    if not isinstance(disposition, str) or disposition not in DECISIONS:
        raise ValueError("invalid_disposition")
    if not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 2000:
        raise ValueError("reason_required")
    try:
        reason.encode("utf-8")
    except UnicodeError:
        raise ValueError("invalid_reason_unicode") from None
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("invalid_revision")
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute("SELECT revision,disposition FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise ValueError("unknown_run")
        prior = db.execute("SELECT revision,disposition,reason,reviewer FROM reviews WHERE run_id=? AND event_key=?",
                           (run_id,event_key)).fetchone()
        if prior:
            if (prior[1] != disposition or prior[2] != reason.strip() or
                    prior[3] != reviewer or expected_revision != prior[0]-1):
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


def _get_run(db, run_id):
    row = db.execute("SELECT run_id,snapshot_id,receipt_sha256,candidate_json,evidence_json,revision,disposition,execution_json,provenance_status "
                     "FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not row:
        raise ValueError("unknown_run")
    history = db.execute("SELECT revision,reviewer,disposition,reason,at FROM reviews WHERE run_id=? ORDER BY revision", (run_id,)).fetchall()
    return dict(run_id=row[0],snapshot_id=row[1],receipt_sha256=row[2],
                candidate=json.loads(row[3]),evidence=json.loads(row[4]),revision=row[5],disposition=row[6],
                execution=json.loads(row[7]) if row[7] else execution_metadata({}),
                provenance_status=row[8],
                history=[dict(revision=h[0],reviewer=h[1],disposition=h[2],reason=h[3],at=h[4]) for h in history])




def get_run(db, run_id):
    # One consistent read snapshot for the revision and its append-only history.
    owned = not db.in_transaction
    if owned: db.execute("BEGIN")
    try:
        return _get_run(db, run_id)
    finally:
        if owned: db.execute("ROLLBACK")


def handler_factory(db_path: Path, token: str):
    if not isinstance(token, str) or len(token) < 32:
        raise ValueError("review_token_too_short")
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            # Request paths and arbitrary headers must not enter credential logs.
            pass

        def local_request(self):
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host") not in allowed:
                self.reply(403, {"error": "host_not_allowed"})
                return False
            origin = self.headers.get("Origin")
            if origin is not None and origin not in {"http://" + host for host in allowed}:
                self.reply(403, {"error": "origin_not_allowed"})
                return False
            return True

        def reply(self, status, obj):
            blob = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

        def authorised(self):
            supplied = self.headers.get("Authorization", "")
            return compare_digest(supplied.encode(), ("Bearer " + token).encode())

        def do_GET(self):
            if not self.local_request(): return
            route = urlsplit(self.path).path
            if route == "/":
                blob = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type","text/html; charset=utf-8")
                self.send_header("Cache-Control","no-store")
                self.send_header("X-Content-Type-Options","nosniff")
                self.send_header("Content-Security-Policy","default-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
                self.send_header("Content-Length",str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)
                return
            if not self.authorised():
                self.reply(401,{"error":"unauthorised"});return
            match = re.fullmatch(r"/api/runs/([a-zA-Z0-9_-]{1,100})",route)
            if not match:
                self.reply(404,{"error":"not_found"});return
            with closing(connect(db_path)) as db:
                try:self.reply(200,get_run(db,match[1]))
                except ValueError as exc:self.reply(404,{"error":str(exc)})

        def do_POST(self):
            if not self.local_request(): return
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                self.reply(415, {"error": "json_required"})
                return
            if not self.authorised():
                self.reply(401,{"error":"unauthorised"});return
            match = re.fullmatch(r"/api/runs/([a-zA-Z0-9_-]{1,100})/reviews",urlsplit(self.path).path)
            if not match:
                self.reply(404,{"error":"not_found"});return
            try:
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or self.headers.get("Transfer-Encoding"):
                    raise ValueError("invalid_body_size")
                length = int(lengths[0])
                if not 0 < length <= MAX_REVIEW_BODY:
                    self.reply(413, {"error": "invalid_body_size"}); return
                self.connection.settimeout(10)
                blob = self.rfile.read(length)
                if len(blob) != length: raise ValueError("invalid_body_size")
                payload = strict_json(blob)
                if not isinstance(payload,dict) or set(payload) != {"expected_revision","event_key","disposition","reason"}:
                    raise ValueError("invalid_fields")
                with closing(connect(db_path)) as db:
                    outcome=review(db,run_id=match[1],reviewer="local_operator",
                                   **payload)
                self.reply(200,outcome)
            except ValueError as exc:
                self.reply(409,{"error":str(exc) if str(exc) in {
                    "invalid_body_size", "invalid_json", "invalid_fields", "invalid_run",
                    "invalid_event_key", "invalid_reviewer", "invalid_disposition", "reason_required",
                    "invalid_reason_unicode", "invalid_revision", "unknown_run", "idempotency_conflict",
                    "already_reviewed", "revision_conflict"} else "invalid_request"})
            except (TypeError, UnicodeError):
                self.reply(409, {"error": "invalid_request"})
            except TimeoutError:
                self.reply(408, {"error": "request_timeout"})
            except sqlite3.Error:
                self.reply(503, {"error": "review_storage_unavailable"})
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
        with closing(connect(args.db)) as db:
            print("IMPORTED_RUN="+import_receipt(db,args.import_receipt,root=args.runtime_root))
        return
    token=os.getenv("AFYA_REVIEW_TOKEN","")
    if len(token)<32:raise SystemExit("AFYA_REVIEW_TOKEN must be at least 32 characters")
    server=ThreadingHTTPServer(("127.0.0.1",args.port),handler_factory(args.db,token))
    print(f"REVIEW_UI=http://127.0.0.1:{args.port}/",flush=True)
    server.serve_forever()


if __name__=="__main__":main()
