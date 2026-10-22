"""Review state tests; use only synthetic local receipts."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from afyaevidence.review_server import connect, get_run, import_receipt, review


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.receipt = self.root / "good.json"
        self.receipt.write_text(json.dumps({
            "run_id": "run_example",
            "execution_status": "ready_for_review",
            "evidence_bundle": {"snapshot_id": "synthetic_snapshot"},
            "candidate_brief": {"review_status": "awaiting_human_review",
                                "semantic_review_required": True,
                                "approval": None, "explanation": "unexplained"},
        }))
        self.db = connect(self.root / "reviews.sqlite3")
        self.addCleanup(self.db.close)

    def test_import_and_review(self):
        run_id = import_receipt(self.db, self.receipt, root=self.root)
        self.assertEqual(run_id, "run_example")
        self.assertEqual(import_receipt(self.db, self.receipt, root=self.root), run_id)
        self.assertIsNone(get_run(self.db, run_id)["disposition"])
        args = dict(run_id=run_id, expected_revision=0, event_key="event_1",
                    reviewer="local_operator", disposition="request_more_evidence",
                    reason="Inspect the missing facility reporting evidence.")
        result = review(self.db, **args)
        self.assertEqual(result["revision"], 1)
        self.assertTrue(review(self.db, **args)["replayed"])
        self.assertEqual(get_run(self.db, run_id)["disposition"], "request_more_evidence")
        with self.assertRaisesRegex(ValueError, "already_reviewed"):
            review(self.db, **{**args, "event_key": "event_2"})

    def test_fail_closed(self):
        doc = json.loads(self.receipt.read_text())
        doc["candidate_brief"]["approval"] = True
        self.receipt.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, "human_boundary_invalid"):
            import_receipt(self.db, self.receipt, root=self.root)

    def test_invalid_review_and_conflict(self):
        import_receipt(self.db, self.receipt, root=self.root)
        args = dict(run_id="run_example", expected_revision=0, event_key="review_a",
                    reviewer="operator", disposition="accept", reason="Confirmed on synthetic evidence.")
        with self.assertRaisesRegex(ValueError, "reason_required"):
            review(self.db, **{**args, "reason": "too short"})
        review(self.db, **args)
        with self.assertRaisesRegex(ValueError, "idempotency_conflict"):
            review(self.db, **{**args, "reason": "Changed reason contradicts original."})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 1)

    def test_prevent_outside_import(self):
        external = self.root.parent / "non_runtime_receipt.json"
        external.write_text(self.receipt.read_text())
        self.addCleanup(lambda: external.unlink(missing_ok=True))
        with self.assertRaisesRegex(ValueError, "receipt_outside_runtime"):
            import_receipt(self.db, external, root=self.root)


if __name__ == "__main__":
    unittest.main()
