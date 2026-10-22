"""Dashboard and review-history integration tests."""
from pathlib import Path
import sys
import unittest
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from afyaevidence.review_page import PAGE
from afyaevidence.review_server import connect, get_run, import_receipt, review
import json

class ReviewDashboardTests(unittest.TestCase):
    def test_dashboard_has_safely_rendered_sections(self):
        for section in ('Monthly comparison','Report-version history','Matched-facility contributions',
                        'Review history','Technical JSON','limitations','textContent'):
            self.assertIn(section,PAGE)
        self.assertNotIn('innerHTML',PAGE)

    def test_history_and_immutable_accepted_disposition(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            receipt=root/"synthetic.json"
            receipt.write_text(json.dumps(dict(
                run_id="run_demo",execution_status="ready_for_review",
                evidence_bundle=dict(snapshot_id="snap_demo",evidence_records=[],
                                     metrics=[],matched_facility_contributions=[]),
                candidate_brief=dict(review_status="awaiting_human_review",
                                     semantic_review_required=True,approval=None,summary="Synthetic demo"))))
            with connect(root/"test.sqlite3") as db:
                self.assertEqual(import_receipt(db,receipt,root=root),"run_demo")
                self.assertEqual(get_run(db,"run_demo")["history"],[])
                review(db,run_id="run_demo",expected_revision=0,event_key="event_001",reviewer="local_operator",
                       disposition="accept",reason="Synthetic evidence reviewed for this example.")
                result=get_run(db,"run_demo")
                self.assertEqual(result["revision"],1)
                self.assertEqual(result["disposition"],"accept")
                self.assertEqual(len(result["history"]),1)
                self.assertEqual(result["history"][0]["disposition"],"accept")
                self.assertEqual(result["candidate"]["approval"],None)

if __name__=="__main__":
    unittest.main()
