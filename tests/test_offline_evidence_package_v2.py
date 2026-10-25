"""Offline Evidence Packages v2 tests: integrity, expiry and safe read-only ZIPs."""
from __future__ import annotations
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/offline_evidence_package_v2.py"
SPEC = importlib.util.spec_from_file_location("offline_v2", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

def receipt():
    evidence_id = "ev_1"
    return {
        "schema_version": "agent-run-1", "execution_status": "ready_for_review",
        "review_status": "awaiting_human_review", "data_mode": "fixture",
        "model_mode": "scripted", "memory_mode": "disabled_fixture",
        "candidate_brief": {
            "summary": "Synthetic reporting artefact identified",
            "explanation": "reporting_artefact_supported",
            "review_status": "awaiting_human_review",
            "semantic_review_required": True, "approval": None,
            "numerical_statements": [{
                "metric_ref": "m1", "text": "comparison / all_available / canonical: positive_total = 100 episodes",
                "evidence_ids": [evidence_id]}],
            "evidence_ids": [evidence_id],
            "limitations": ["synthetic_data", "no_causal_attribution"],
            "next_checks": ["human_review"]},
        "evidence_bundle": {
            "data_mode": "fixture", "snapshot_id": "ss_" + "1" * 64,
            "metrics": [{"metric_ref": "m1", "period": "comparison", "cohort": "all_available",
                         "view": "canonical", "name": "positive_total", "value": 100,
                         "unit": "episodes", "evidence_ids": [evidence_id]}],
            "evidence_records": [{"evidence_id": evidence_id,
                                  "record": {"raw_private_record": "DO_NOT_INCLUDE"}}]}}
def bytes_receipt():
    return MOD.canonical(receipt())

class OfflineEvidenceV2Tests(unittest.TestCase):
    def test_valid_portable_package_and_private_data_exclusion(self):
        now = datetime(2026, 10, 25, tzinfo=timezone.utc)
        files = MOD.build(bytes_receipt(), now, 48)
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "package.zip"
            with zipfile.ZipFile(archive, "w") as z:
                for name in MOD.NAMES:
                    z.writestr(name, files[name])
            result = MOD.inspect(archive, None, now + timedelta(hours=1))
            self.assertEqual(result["freshness"], "WITHIN_REVIEW_WINDOW")
            stale = MOD.inspect(archive, None, now + timedelta(hours=49))
            self.assertEqual(stale["freshness"], "STALE")
            self.assertEqual(set(files), set(MOD.NAMES))
            raw = b"".join(files.values())
            self.assertNotIn(b"DO_NOT_INCLUDE", raw)
            self.assertNotIn(b"<script", files["briefcase.html"])
            self.assertNotIn(b"<form", files["briefcase.html"])
            self.assertIn(b"may now be stale", files["briefcase.html"])
            self.assertIn("source_receipt_sha256", json.loads(files["manifest.json"]))

    def test_changed_html_without_manifest_update_rejected(self):
        now = datetime(2026, 10, 25, tzinfo=timezone.utc)
        files = MOD.build(bytes_receipt(), now, 48)
        files["briefcase.html"] += b"UNAUTHORISED_CHANGE"
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/"altered.zip"
            with zipfile.ZipFile(p,"w") as z:
                for name in MOD.NAMES:
                    z.writestr(name, files[name])
            with self.assertRaises(ValueError):
                MOD.inspect(p, None, now)

    def test_zip_extra_member_or_path_traversal_rejected(self):
        now = datetime(2026, 10, 25, tzinfo=timezone.utc)
        files = MOD.build(bytes_receipt(), now, 48)
        for extra in ("../escape.txt", "extra.txt"):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as temp:
                p = Path(temp)/"unsafe.zip"
                with zipfile.ZipFile(p,"w") as z:
                    for name in MOD.NAMES:
                        z.writestr(name, files[name])
                    z.writestr(extra, "malicious")
                with self.assertRaises(ValueError):
                    MOD.inspect(p,None,now)

    def test_wrong_out_of_band_package_hash_rejected(self):
        now = datetime(2026, 10, 25, tzinfo=timezone.utc)
        files = MOD.build(bytes_receipt(), now, 48)
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/"valid.zip"
            with zipfile.ZipFile(p,"w") as z:
                for name in MOD.NAMES:
                    z.writestr(name, files[name])
            with self.assertRaises(ValueError):
                MOD.inspect(p,"0"*64,now)

    def test_invalid_receipt_not_packaged(self):
        doc = receipt()
        doc["data_mode"] = "zetaris"
        with self.assertRaises(ValueError):
            MOD.build(MOD.canonical(doc),datetime.now(timezone.utc),48)
        doc = receipt()
        doc["candidate_brief"]["approval"] = "accept"
        with self.assertRaises(ValueError):
            MOD.build(MOD.canonical(doc),datetime.now(timezone.utc),48)

    def test_create_cli_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            receipt_path = home/"receipt.json"
            receipt_path.write_bytes(bytes_receipt())
            output = home/"portable.zip"
            cmd = [sys.executable,str(SCRIPT),"create","--receipt",str(receipt_path),
                   "--output",str(output)]
            first = subprocess.run(cmd,capture_output=True,text=True,timeout=20)
            self.assertEqual(first.returncode,0,first.stdout+first.stderr)
            self.assertIn("OFFLINE_PACKAGE=PASS",first.stdout)
            original = output.read_bytes()
            second = subprocess.run(cmd,capture_output=True,text=True,timeout=20)
            self.assertEqual(second.returncode,2)
            self.assertEqual(original,output.read_bytes())
            self.assertEqual(bytes_receipt(),receipt_path.read_bytes())

if __name__ == "__main__":
    unittest.main()
