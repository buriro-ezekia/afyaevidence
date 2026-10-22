from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from afyaevidence.identity_page import JS

class IdentityUITests(unittest.TestCase):
    def test_actual_ui_logic_metrics_identity_and_failure_clearing(self):
        with tempfile.TemporaryDirectory() as temp:
            js=Path(temp)/'identity.js';js.write_text(JS)
            check=subprocess.run(['node','--check',str(js)],capture_output=True,text=True,timeout=10)
            self.assertEqual(check.returncode,0,check.stderr)
            result=subprocess.run(['node',str(ROOT/'tests/identity_dom_check.js'),str(js)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('IDENTITY_UI_LOGIC=PASS',result.stdout)

if __name__=='__main__':unittest.main()
