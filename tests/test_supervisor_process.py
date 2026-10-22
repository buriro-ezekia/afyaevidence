"""Real Linux processes; synthetic worker only, never a model call or source edit."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SOURCE = str(Path(__file__).resolve().parents[1] / "src")
WORKER = '''
import json, os, pathlib, signal, subprocess, sys, time
root = pathlib.Path(os.environ["TEST_ROOT"])
mode = os.environ["TEST_MODE"]
if mode == "ignore": signal.signal(signal.SIGTERM, signal.SIG_IGN)
child = subprocess.Popen([sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(90)"])
time.sleep(.1)
(root / "pids.json").write_text(json.dumps([os.getpid(), child.pid]))
if mode == "exit":
    pathlib.Path(sys.argv[sys.argv.index("--output")+1]).write_text('{"execution_status":"ready_for_review"}')
else:
    time.sleep(90)
'''
RUNNER = '''
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
from afyaevidence.supervisor import supervise
root=pathlib.Path(sys.argv[2])
print(json.dumps(supervise([sys.executable,"-m","afyaevidence.agent_cli","--output",str(root/sys.argv[4])], state_dir=root/"jobs", timeout=int(sys.argv[3]))), flush=True)
'''

@unittest.skipUnless(sys.platform == "linux", "Linux process groups and subreaper required")
class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        package = self.root / "afyaevidence"
        package.mkdir()
        (package / "__init__.py").write_text("")
        (package / "agent_cli.py").write_text(WORKER)
        self.processes = []
        self.pids = []

    def tearDown(self):
        if self.pids:
            try: os.killpg(self.pids[0], signal.SIGKILL)
            except ProcessLookupError: pass
        for proc in self.processes:
            if proc.poll() is None:
                proc.terminate()
            try: proc.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
        self.temp.cleanup()

    def launch(self, mode="ignore", timeout=30, output="receipt.json"):
        env = dict(os.environ, PYTHONPATH=str(self.root), TEST_ROOT=str(self.root), TEST_MODE=mode)
        proc = subprocess.Popen([sys.executable,"-c",RUNNER,SOURCE,str(self.root),str(timeout),output],
                                cwd=self.root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.processes.append(proc)
        return proc

    def ready(self):
        end = time.monotonic()+8
        while time.monotonic() < end:
            try:
                self.pids = json.loads((self.root/"pids.json").read_text())
                return
            except (FileNotFoundError, ValueError): time.sleep(.02)
        self.fail("worker did not start")

    def result(self, proc):
        out, err = proc.communicate(timeout=15)
        self.assertEqual(proc.returncode, 0, err)
        return json.loads(out)

    def assert_clean(self, result):
        self.assertTrue(result["cleanup_complete"])
        for pid in self.pids:
            with self.assertRaises(ProcessLookupError): os.kill(pid, 0)
        finals = list((self.root/"jobs").glob("*.final.json"))
        self.assertEqual(len(finals), 1)
        self.assertEqual(json.loads(finals[0].read_text()), result)

    def test_sigterm_keeps_ownership_during_cleanup_then_releases(self):
        proc = self.launch()
        self.ready()
        proc.send_signal(signal.SIGTERM)
        time.sleep(.2)
        competing = self.result(self.launch(output="second.json"))
        self.assertEqual(competing["state"], "busy")
        self.assertFalse(list((self.root/"jobs").glob("*.final.json")))
        result = self.result(proc)
        self.assertEqual(result["state"], "interrupted")
        self.assertEqual(result["termination_signal"], signal.SIGTERM)
        self.assert_clean(result)
        next_result = self.result(self.launch(mode="exit", output="second.json"))
        self.assertEqual(next_result["state"], "finished")

    def test_sigint_interrupts_without_replaying(self):
        proc = self.launch()
        self.ready()
        proc.send_signal(signal.SIGINT)
        result = self.result(proc)
        self.assertEqual(result["state"], "cancelled")
        self.assert_clean(result)
        self.assertFalse((self.root/"receipt.json").exists())
        self.assertEqual(len(list((self.root/"jobs").glob("job_*.json"))), 2)

    def test_timeout_kills_term_ignoring_group(self):
        proc = self.launch(timeout=1)
        self.ready()
        result = self.result(proc)
        self.assertEqual(result["state"], "timed_out")
        self.assert_clean(result)

    def test_exited_leader_still_cleans_descendants(self):
        proc = self.launch(mode="exit")
        self.ready()
        result = self.result(proc)
        self.assertEqual(result["state"], "finished")
        self.assert_clean(result)

    def test_sigkill_retains_inherited_lock_and_requires_reconciliation(self):
        proc = self.launch()
        self.ready()
        proc.kill()
        proc.communicate(timeout=3)
        self.assertEqual(self.result(self.launch(output="second.json"))["state"], "busy")
        os.killpg(self.pids[0], signal.SIGKILL)
        time.sleep(.2)
        self.assertEqual(self.result(self.launch(output="second.json"))["state"], "needs_operator_reconciliation")
        self.assertFalse(list((self.root/"jobs").glob("*.final.json")))
        self.assertFalse((self.root/"second.json").exists())

if __name__ == "__main__": unittest.main()
