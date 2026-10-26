"""Hackathon demo gate tests: evidence, live-mode honesty and safe failures."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import json

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_hackathon_demo.py"
spec = importlib.util.spec_from_file_location("hackathon_gate", SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def receipt(data="fixture", model="scripted", memory="disabled_fixture"):
    return {
        "schema_version": "agent-run-1",
        "execution_status": "ready_for_review",
        "review_status": "awaiting_human_review",
        "data_mode": data, "model_mode": model, "memory_mode": memory,
        "evidence_bundle": {"snapshot_id": "ss_" + "a"*64, "data_mode": data},
        "candidate_brief": {"approval": None, "review_status": "awaiting_human_review",
                            "semantic_review_required": True,
                            "evidence_ids": ["ev_a"]},
    }


class HackathonGateTests(unittest.TestCase):
    def test_fixture_mode_success(self):
        self.assertEqual(gate.assess(receipt(), "fixture")["review"],
                         "awaiting_human_review")

    def test_integrated_mode_must_be_explicit(self):
        self.assertEqual(gate.assess(receipt("zetaris", "ollama", "hmem_reference"),
                                     "integrated")["review"], "awaiting_human_review")
        with self.assertRaisesRegex(ValueError, "mode_mismatch"):
            gate.assess(receipt(), "integrated")

    def test_never_accept_approved_or_failed(self):
        doc = receipt()
        doc["candidate_brief"]["approval"] = "accept"
        with self.assertRaises(ValueError):
            gate.assess(doc, "fixture")
        doc = receipt()
        doc["execution_status"] = "failed"
        with self.assertRaises(ValueError):
            gate.assess(doc, "fixture")

    def test_evidence_and_review_boundary_required(self):
        doc = receipt()
        doc["candidate_brief"]["evidence_ids"] = []
        with self.assertRaises(ValueError):
            gate.assess(doc, "fixture")
        doc = receipt()
        doc["review_status"] = "approved"
        with self.assertRaises(ValueError):
            gate.assess(doc, "fixture")

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"receipt.json"
            path.write_text('{"data_mode":"fixture","data_mode":"zetaris"}')
            with self.assertRaisesRegex(ValueError, "duplicate_json_key"):
                gate.read(path)


if __name__ == "__main__":
    unittest.main()
