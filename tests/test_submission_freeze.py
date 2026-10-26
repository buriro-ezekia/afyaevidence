"""Freeze audit checks reject altered witness evidence without exposing source data."""
import importlib.util
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/audit_submission_freeze.py"
SPEC = importlib.util.spec_from_file_location("submission_freeze", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def witness(raw):
    return {
        "schema": "afya-hackathon-witness-1",
        "source_receipts": {
            "integrated_sha256": sha256(raw).hexdigest(),
            "fixture_sha256": "a" * 64,
        },
        "integrated": {
            "data_mode": "zetaris", "model_mode": "ollama",
            "memory_mode": "hmem_reference",
            "execution_status": "ready_for_review",
            "review_status": "awaiting_human_review",
            "explanation_category": "reporting_artefact_supported",
            "recalled_context_count": 0,
            "memory_pending_sync": 0,
        },
        "human_review": "REQUIRED",
        "production_release": "BLOCKED",
        "network_and_service_attestation": "NOT_INDEPENDENTLY_VERIFIED",
    }


class SubmissionFreezeTests(unittest.TestCase):
    def test_exact_integrated_digest_passes(self):
        raw = b"synthetic example receipt bytes"
        self.assertEqual(MOD.validate(witness(raw), raw,
                         expected_sha=sha256(raw).hexdigest()), sha256(raw).hexdigest())

    def test_tampered_receipt_rejected(self):
        raw = b"synthetic example receipt bytes"
        with self.assertRaisesRegex(ValueError, "integrated_receipt_digest_mismatch"):
            MOD.validate(witness(raw), raw + b"altered", expected_sha=sha256(raw).hexdigest())

    def test_unverified_or_approved_review_rejected(self):
        raw = b"synthetic example receipt bytes"
        doc = witness(raw)
        doc["integrated"]["review_status"] = "approved"
        with self.assertRaises(ValueError):
            MOD.validate(doc, raw, expected_sha=sha256(raw).hexdigest())
        doc = witness(raw)
        doc["network_and_service_attestation"] = "VERIFIED"
        with self.assertRaises(ValueError):
            MOD.validate(doc, raw, expected_sha=sha256(raw).hexdigest())

    def test_existing_destination_reports_safe_reason(self):
        with tempfile.TemporaryDirectory() as home:
            folder = Path(home)
            out = folder / "freeze.json"
            out.write_text("existing report", encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(SCRIPT),
                "--witness", str(folder / "missing-witness.json"),
                "--integrated-receipt", str(folder / "missing-receipt.json"),
                "--output", str(out),
            ], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 2)
            self.assertIn("SUBMISSION_FREEZE_REASON=output_already_exists", result.stdout)
            self.assertEqual(out.read_text(), "existing report")

    def test_missing_integrated_receipt_reports_specific_reason(self):
        with tempfile.TemporaryDirectory() as home:
            folder = Path(home)
            out = folder / "freeze.json"
            result = subprocess.run([
                sys.executable, str(SCRIPT),
                "--witness", str(folder / "absent-witness.json"),
                "--integrated-receipt", str(folder / "absent-integrated.json"),
                "--output", str(out),
            ], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 2)
            self.assertIn("SUBMISSION_FREEZE_REASON=integrated_receipt_missing", result.stdout)
            self.assertFalse(out.exists())

    def test_missing_file_blocks_and_never_writes(self):
        with tempfile.TemporaryDirectory() as home:
            folder = Path(home)
            out = folder / "freeze.json"
            result = subprocess.run([
                sys.executable, str(SCRIPT),
                "--witness", str(folder / "missing-witness.json"),
                "--integrated-receipt", str(folder / "missing-receipt.json"),
                "--output", str(out)
            ], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 2)
            self.assertIn("SUBMISSION_FREEZE=BLOCKED", result.stdout)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
