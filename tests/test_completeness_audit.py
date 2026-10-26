"""Completeness audit is read-only and must never assert release readiness."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_project_completeness.py"


class CompletenessAuditTests(unittest.TestCase):
    def test_missing_tree_blocks_without_creating_files(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 1)
            self.assertIn("PROJECT_STRUCTURE=FAIL", result.stdout)
            self.assertIn("PROJECT_RELEASE=BLOCKED", result.stdout)
            self.assertEqual(list(root.iterdir()), [])

    def test_json_report_never_claims_security_or_production_pass(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            out = root / "report.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(ROOT), "--json", str(out)],
                capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(out.read_text())
            self.assertEqual(report["release_decision"], "BLOCKED")
            self.assertEqual(report["release_gates"]["independent_security_review"], "PENDING")
            self.assertEqual(report["release_gates"]["keycloak_container_security"],
                             "BLOCKED_BY_REPORTED_CVES")
            self.assertIn("README.md", report["readmes_found"])
            self.assertIn("bridges/hmem/upstream/README.md", report["readmes_found"])
            self.assertEqual(report["readme_human_editorial_review"], "REQUIRED")

    def test_report_is_never_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "report.json"
            out.write_text("original")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(ROOT), "--json", str(out)],
                capture_output=True, text=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(out.read_text(), "original")


if __name__ == "__main__":
    unittest.main()
