"""Supervisor process and exclusive-worker regression checks (no real model)."""
import fcntl
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from afyaevidence.supervisor import supervise

class FakeProcess:
    pid=123456
    def __init__(self,*args,**kwargs):self.returncode=0
    def wait(self,timeout=None):return self.returncode
    def poll(self):return self.returncode

class SupervisorTests(unittest.TestCase):
    def test_busy_worker_does_not_spawn_child(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            state=root/"jobs"
            state.mkdir()
            with (state/".worker.lock").open("a+") as lock:
                fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                with patch("afyaevidence.supervisor.subprocess.Popen",side_effect=AssertionError("spawned")):
                    result=supervise([sys.executable,"-m","afyaevidence.agent_cli",
                                      "--output",str(root/"receipt.json")],state_dir=state)
                self.assertEqual(result["state"],"busy")
                fcntl.flock(lock.fileno(),fcntl.LOCK_UN)

    def test_failed_child_retains_start_and_final_events(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            with patch("afyaevidence.supervisor.subprocess.Popen",return_value=FakeProcess()):
                result=supervise([sys.executable,"-m","afyaevidence.agent_cli",
                                  "--output",str(root/"receipt.json")],state_dir=root/"jobs")
            self.assertEqual(result["state"],"failed")
            records=list((root/"jobs").glob("job_*.json"))
            self.assertEqual(len(records),2)
            self.assertEqual({json.loads(p.read_text())["state"] for p in records},{"running","failed"})

    def test_unsupported_executable_and_existing_receipt_fail_closed(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            args=[sys.executable,"-m","afyaevidence.agent_cli","--output",str(root/"receipt.json")]
            with self.assertRaises(ValueError):
                supervise(["/bin/sh",*args[1:]],state_dir=root/"jobs")
            (root/"receipt.json").write_text("{}")
            with self.assertRaises(ValueError):
                supervise(args,state_dir=root/"jobs")

    def test_review_capability_is_not_inherited_by_worker_and_spawn_failure_is_final(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            args=[sys.executable,"-m","afyaevidence.agent_cli","--output",str(root/"receipt.json")]
            with patch.dict(os.environ,{"AFYA_REVIEW_TOKEN":"test-only-review-capability"}), patch(
                    "afyaevidence.supervisor.subprocess.Popen",side_effect=OSError("launch failed")) as spawn:
                result=supervise(args,state_dir=root/"jobs")
                self.assertNotIn("AFYA_REVIEW_TOKEN",spawn.call_args.kwargs["env"])
            self.assertEqual(result["state"],"failed")
            self.assertTrue(result["cleanup_complete"])
            with patch("afyaevidence.supervisor.subprocess.Popen",return_value=FakeProcess()):
                self.assertEqual(supervise(args,state_dir=root/"jobs")["state"],"failed")

if __name__=="__main__":unittest.main()
