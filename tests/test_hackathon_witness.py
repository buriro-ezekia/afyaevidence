"""Hackathon witness uses allowlisted fields and never exposes receipt secrets."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/prepare_hackathon_witness.py"
SPEC = importlib.util.spec_from_file_location("witness", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def receipt(*, integrated=False):
    mode = "zetaris" if integrated else "fixture"
    return {
        "schema_version": "agent-run-1",
        "data_mode": mode,
        "model_mode": "ollama" if integrated else "scripted",
        "memory_mode": "hmem_reference" if integrated else "disabled_fixture",
        "execution_status": "ready_for_review",
        "review_status": "awaiting_human_review",
        "execution_profile": "cpu",
        "model_calls": 2, "model_call_limit": 2, "tool_calls": 5, "repairs": 0,
        "memory_pending_sync": 0, "reference_aliases": {"context": {}},
        "evidence_bundle": {
            "snapshot_id": "ss_" + "a"*64, "data_mode": mode,
            "secret": "never-publish-the-input-secret",
        },
        "candidate_brief": {
            "approval": None, "review_status": "awaiting_human_review",
            "semantic_review_required": True, "evidence_ids": ["ev_1"],
            "explanation": "reporting_artefact_supported",
            "summary": "never-publish-the-input-secret",
        },
    }


class WitnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        folder = Path(self.tmp.name)
        self.fixture = folder / "fixture.json"
        self.actual = folder / "integrated.json"
        self.out = folder / "witness.json"
        self.fixture.write_text(json.dumps(receipt()), encoding="utf-8")
        self.actual.write_text(json.dumps(receipt(integrated=True)), encoding="utf-8")

    def run_cli(self):
        return subprocess.run([sys.executable, str(SCRIPT),
            "--fixture-receipt", str(self.fixture),
            "--integrated-receipt", str(self.actual), "--out", str(self.out)],
            capture_output=True, text=True, timeout=15)

    def test_witness_validates_modes_and_redacts_untrusted_text(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertEqual(data["integrated"]["explanation_category"], "reporting_artefact_supported")
        self.assertEqual(data["integrated"]["recalled_context_count"], 0)
        self.assertNotIn("never-publish-the-input-secret", self.out.read_text(encoding="utf-8"))
        self.assertIn("HACKATHON_WITNESS=PASS", result.stdout)

    def test_existing_witness_never_overwritten(self):
        self.assertEqual(self.run_cli().returncode, 0)
        first = self.out.read_bytes()
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertEqual(first, self.out.read_bytes())

    def test_failed_review_or_fixture_cannot_generate_witness(self):
        doc = receipt(integrated=True)
        doc["candidate_brief"]["approval"] = "approved"
        self.actual.write_text(json.dumps(doc), encoding="utf-8")
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertFalse(self.out.exists())

    def test_inconsistent_model_budget_is_blocked(self):
        doc = receipt(integrated=True)
        doc["model_calls"] = 4
        doc["model_call_limit"] = 2
        self.actual.write_text(json.dumps(doc), encoding="utf-8")
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
