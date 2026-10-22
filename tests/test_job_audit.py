"""Restart audit is read-only and never treats missing final events as success."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from afyaevidence.job_audit import audit_jobs

class RestartAuditTests(unittest.TestCase):
    def test_missing_final_is_not_restarted_or_relabelled(self):
        with TemporaryDirectory() as d:
            directory=Path(d)
            source=directory/"job_test.json"
            source.write_text(json.dumps({"job_id":"job_test","state":"running"}))
            self.assertEqual(audit_jobs(directory),[{"job_id":"job_test","state":"needs_operator_reconciliation"}])
            self.assertFalse((directory/"job_test.final.json").exists())
            (directory/"job_test.final.json").write_text(json.dumps({"job_id":"job_test","state":"failed"}))
            self.assertEqual(audit_jobs(directory)[0]["state"],"finalised")
            self.assertEqual(json.loads(source.read_text())["state"],"running")

    def test_corrupt_events_stay_visible(self):
        with TemporaryDirectory() as d:
            p=Path(d)/"job_bad.json"
            p.write_text("{oops")
            self.assertEqual(audit_jobs(Path(d))[0]["state"],"corrupt_event_record")

    def test_invalid_final_states_and_orphans_never_clear_restart_gate(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            start=root/"job_test.json"
            final=root/"job_test.final.json"
            start.write_text(json.dumps({"job_id":"job_test","state":"running"}))
            for value in ([], {"job_id":"job_test","state":"running"},
                          {"job_id":"job_test","state":[]},
                          {"job_id":"job_test","state":"failed","cleanup_complete":False}):
                final.write_text(json.dumps(value))
                self.assertEqual(audit_jobs(root)[0]["state"],"invalid_final_record")
            start.unlink()
            self.assertEqual(audit_jobs(root)[0]["state"],"corrupt_event_record")
            self.assertTrue(final.exists())

if __name__=="__main__":unittest.main()
