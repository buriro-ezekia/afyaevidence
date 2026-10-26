"""Node preflight regression tests for the H-MEM verification launcher."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess, TimeoutExpired
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/verify_identity_worker.py'
SPEC=importlib.util.spec_from_file_location('identity_verifier',SCRIPT)
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

class NodePreflightTests(unittest.TestCase):
    @patch.object(MOD.subprocess,'run')
    def test_node24_accepted(self,run):
        run.return_value=CompletedProcess(['node','--version'],0,'v24.12.0\n','')
        self.assertEqual(MOD.node_preflight(),(True,'v24.12.0'))

    @patch.object(MOD.subprocess,'run')
    def test_node22_rejected(self,run):
        run.return_value=CompletedProcess(['node','--version'],0,'v22.23.2\n','')
        self.assertEqual(MOD.node_preflight(),(False,'v22.23.2'))

    @patch.object(MOD.subprocess,'run',side_effect=FileNotFoundError())
    def test_missing_node_rejected(self,run):
        self.assertEqual(MOD.node_preflight(),(False,'NOT_AVAILABLE'))

    @patch.object(MOD.subprocess,'run',side_effect=TimeoutExpired('node',8))
    def test_node_timeout_rejected(self,run):
        self.assertEqual(MOD.node_preflight(),(False,'NOT_AVAILABLE'))

    @patch.object(MOD.subprocess,'run')
    def test_malformed_version_rejected(self,run):
        run.return_value=CompletedProcess(['node','--version'],0,'v24-dirty\n','')
        self.assertEqual(MOD.node_preflight(),(False,'v24-dirty'))

if __name__ == '__main__':
    unittest.main()
