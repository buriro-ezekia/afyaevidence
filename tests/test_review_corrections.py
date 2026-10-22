"""Provenance migration, immutable imports and real HTTP boundary regressions."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from hashlib import sha256
import http.client
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from afyaevidence.review_server import (SCHEMA, MAX_REVIEW_BODY, connect, get_run,
    import_receipt, review, handler_factory)
from test_review_http import server, request


def receipt(run_id="run_modes", **metadata):
    return dict(run_id=run_id, execution_status="ready_for_review",
        data_mode="zetaris", model_mode="ollama", model="qwen2.5:1.5b",
        memory_mode="hmem_reference", execution_profile="cpu", memory_reads=1,
        live_model="PASS", verification={"source": "PASS"},
        evidence_bundle=dict(snapshot_id="ss_test", data_mode="zetaris",
            model_mode="not_run", memory_mode="not_run"),
        candidate_brief=dict(review_status="awaiting_human_review",
            semantic_review_required=True, approval=None), **metadata)


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "receipt.json"
        self.path.write_text(json.dumps(receipt()), encoding="utf-8")
        self.dbfile = self.root / "reviews.sqlite3"

    def import_run(self):
        with closing(connect(self.dbfile)) as db:
            return import_receipt(db, self.path, root=self.root)

    def args(self, **changes):
        return dict(dict(run_id="run_modes", expected_revision=0, event_key="event_one",
            reviewer="local_operator", disposition="accept", reason="Reviewed synthetic evidence."), **changes)

    def test_actual_and_fixture_execution_metadata_are_top_level(self):
        self.import_run()
        with closing(connect(self.dbfile)) as db:
            run = get_run(db, "run_modes")
            self.assertEqual(run["execution"]["model_mode"], "ollama")
            self.assertEqual(run["execution"]["memory_mode"], "hmem_reference")
            self.assertEqual(run["execution"]["verification"], {"source": "PASS"})
            self.assertEqual(run["execution"]["model"], "qwen2.5:1.5b")
            self.assertEqual(run["execution"]["execution_profile"], "cpu")
            self.assertEqual(run["evidence"]["model_mode"], "not_run")
            self.assertEqual(run["receipt_sha256"], sha256(self.path.read_bytes()).hexdigest())
        doc = receipt("run_fixture")
        doc.update(data_mode="fixture", model_mode="scripted", memory_mode="disabled_fixture")
        other = self.root / "fixture.json"
        other.write_text(json.dumps(doc))
        with closing(connect(self.dbfile)) as db:
            import_receipt(db, other, root=self.root)
            run = get_run(db, "run_fixture")
            self.assertEqual(run["execution"]["data_mode"], "fixture")
            self.assertEqual(run["execution"]["model_mode"], "scripted")
            self.assertEqual(run["execution"]["memory_mode"], "disabled_fixture")

    def legacy(self):
        doc = receipt()
        db = sqlite3.connect(self.dbfile)
        db.executescript(SCHEMA)
        values = ("run_modes", str(self.path.resolve()), sha256(self.path.read_bytes()).hexdigest(),
            "ss_test", json.dumps(doc["candidate_brief"]), json.dumps(doc["evidence_bundle"]),
            "original timestamp", 1, "accept")
        db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)", values)
        db.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?,?)",
            ("run_modes",1,"old_event","original_operator","accept","Original accepted reason.","original time"))
        db.commit()
        history = db.execute("SELECT * FROM reviews").fetchall()
        db.close()
        return values, history

    def test_legacy_migration_keeps_accepted_disposition_hash_and_history(self):
        values, history = self.legacy()
        for _ in range(2):
            with closing(connect(self.dbfile)) as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 2)
                self.assertEqual(db.execute("SELECT * FROM runs").fetchone()[:9], values)
                self.assertEqual(db.execute("SELECT * FROM reviews").fetchall(), history)
                run = get_run(db, "run_modes")
                self.assertEqual(run["execution"]["model_mode"], "ollama")
                self.assertEqual(run["disposition"], "accept")
                self.assertEqual(import_receipt(db, self.path, root=self.root), "run_modes")
                with self.assertRaisesRegex(ValueError, "already_reviewed"):
                    review(db, **self.args(expected_revision=1))
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone(), ("ok",))

    def test_legacy_missing_and_changed_original_are_explicit_not_inferred(self):
        for changed in (False, True):
            with self.subTest(changed=changed):
                # Separate DBs so each upgrade actually executes.
                self.dbfile = self.root / (str(changed)+".sqlite3")
                self.path.write_text(json.dumps(receipt()))
                values, history = self.legacy()
                if changed:
                    doc=receipt();doc["model_mode"]="scripted"
                    self.path.write_text(json.dumps(doc))
                else:
                    self.path.unlink()
                with closing(connect(self.dbfile)) as db:
                    run=get_run(db,"run_modes")
                    self.assertIsNone(run["execution"]["model_mode"])
                    self.assertEqual(run["provenance_status"], "legacy_hash_mismatch" if changed else "legacy_unavailable")
                    self.assertEqual(db.execute("SELECT * FROM runs").fetchone()[:9], values)
                    self.assertEqual(db.execute("SELECT * FROM reviews").fetchall(),history)
                self.path.write_text(json.dumps(receipt()))
                with closing(connect(self.dbfile)) as db:
                    import_receipt(db,self.path,root=self.root)
                    self.assertEqual(get_run(db,"run_modes")["execution"]["model_mode"],"ollama")

    def test_conflicting_paths_ids_and_changed_bytes_rollback_without_replacing_review(self):
        self.import_run()
        original = self.path.read_bytes()
        with closing(connect(self.dbfile)) as db:
            review(db, **self.args())
            before = get_run(db, "run_modes")
            self.assertEqual(import_receipt(db, self.path, root=self.root), "run_modes")
            other = self.root / "other.json"
            other.write_bytes(original)
            with self.assertRaisesRegex(ValueError, "immutable_run_conflict"):
                import_receipt(db, other, root=self.root)
            for doc in (receipt("run_other"), dict(receipt(), model="changed")):
                self.path.write_text(json.dumps(doc))
                with self.assertRaisesRegex(ValueError, "immutable_(path|run)_conflict"):
                    import_receipt(db, self.path, root=self.root)
                self.assertEqual(get_run(db, "run_modes"), before)
                self.assertEqual(db.execute("SELECT count(*) FROM runs").fetchone()[0],1)
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.path.write_bytes(original)

    def test_legacy_content_mismatch_cannot_be_hidden_by_reimport(self):
        self.legacy()
        with sqlite3.connect(self.dbfile) as db:
            db.execute("UPDATE runs SET snapshot_id='different_snapshot'")
        with closing(connect(self.dbfile)) as db:
            self.assertEqual(get_run(db,"run_modes")["provenance_status"],"legacy_content_mismatch")
            with self.assertRaisesRegex(ValueError,"immutable_content_conflict"):
                import_receipt(db,self.path,root=self.root)
            self.assertEqual(get_run(db,"run_modes")["disposition"],"accept")
            self.assertIsNone(get_run(db,"run_modes")["execution"]["model_mode"])

    def test_retry_binds_actor_revision_and_concurrent_submissions(self):
        self.import_run()
        barrier=threading.Barrier(2)
        def submit(key):
            with closing(connect(self.dbfile)) as db:
                barrier.wait(timeout=5)
                try:return review(db, **self.args(event_key=key))
                except ValueError as exc:return str(exc)
        with ThreadPoolExecutor(2) as pool:
            a=pool.submit(submit,"event_a");b=pool.submit(submit,"event_b")
            results=[a.result(),b.result()]
        self.assertEqual(sum(isinstance(r,dict) for r in results),1)
        self.assertIn("already_reviewed",results)
        with closing(connect(self.dbfile)) as db:
            winner=db.execute("SELECT event_key FROM reviews").fetchone()[0]
            self.assertTrue(review(db,**self.args(event_key=winner))["replayed"])
            for changes in ({"reviewer":"other_actor"},{"expected_revision":1}):
                with self.assertRaisesRegex(ValueError,"idempotency_conflict"):
                    review(db,**self.args(event_key=winner,**changes))
            self.assertEqual(len(get_run(db,"run_modes")["history"]),1)

    def raw_request(self, port, body, **headers):
        conn=http.client.HTTPConnection("127.0.0.1",port,timeout=5)
        conn.request("POST","/api/runs/run_modes/reviews",body=body,
            headers={"Authorization":"Bearer "+"t"*48,"Content-Type":"application/json",**headers})
        response=conn.getresponse()
        result=response.status,json.loads(response.read())
        conn.close()
        return result

    def test_http_unicode_utf8_and_json_surrogate_escapes(self):
        for escaped in (False,True):
            self.dbfile=self.root/(str(escaped)+".sqlite3")
            self.import_run()
            with server(self.dbfile,"t"*48) as port:
                reason=chr(0x1f600)*2000
                args=self.args(reason=reason);args.pop("run_id");args.pop("reviewer")
                body=json.dumps(args,ensure_ascii=escaped).encode("utf-8")
                self.assertGreater(len(body),4096)
                self.assertEqual(self.raw_request(port,body)[0],200)
                state=request(port,"GET","/api/runs/run_modes","t"*48)[1]
                self.assertEqual(state["history"][0]["reason"],reason)
                self.assertEqual(state["execution"]["model_mode"],"ollama")

    def test_http_invalid_envelopes_and_origins_never_change_history(self):
        self.import_run()
        with server(self.dbfile,"t"*48) as port:
            payload=self.args();payload.pop("run_id");payload.pop("reviewer")
            valid=json.dumps(payload).encode()
            for body, headers, status in (
                (b"x"*(MAX_REVIEW_BODY+1),{},413),
                (b"{broken",{},409),
                (b"[]",{},409),
                (b'{"reason":"x","reason":"y"}',{},409),
                (b"{",{"Content-Type":"text/plain"},415),
                (valid,{"Origin":"http://localhost:invalid"},403),
                (valid,{"Origin":"http://evil.invalid"},403),
                (valid,{"Host":"evil.invalid"},403),
                (json.dumps({**payload,"reason":"x"*2001}).encode(),{},409),
                (json.dumps({**payload,"reviewer":"forged"}).encode(),{},409),
                (json.dumps({**payload,"disposition":[]}).encode(),{},409),
                (json.dumps({**payload,"reason":"\ud800"*10}).encode(),{},409),
                (json.dumps({**payload,"expected_revision":float("nan")}).encode(),{},409),
            ):
                with self.subTest(status=status,headers=headers):
                    self.assertEqual(self.raw_request(port,body,**headers)[0],status)
            state=request(port,"GET","/api/runs/run_modes","t"*48)[1]
            self.assertEqual(state["history"],[])
            self.assertEqual(state["revision"],0)
            self.assertEqual(self.raw_request(port,valid)[0],200)

    def test_empty_auth_configuration_and_forged_receipt_fail_closed(self):
        with self.assertRaises(ValueError):handler_factory(self.dbfile, "")
        for change in (lambda d:d["candidate_brief"].pop("approval"),
                       lambda d:d.update(snapshot_id="other"),
                       lambda d:d.update(evidence_bundle=[])):
            doc=receipt();change(doc);self.path.write_text(json.dumps(doc))
            with closing(connect(self.dbfile)) as db:
                with self.assertRaises(ValueError):import_receipt(db,self.path,root=self.root)
                self.assertEqual(db.execute("SELECT count(*) FROM runs").fetchone()[0],0)


if __name__ == "__main__":unittest.main()
