"""End-to-end v4 CLI acceptance harness, syntax and fail-closed regressions."""
from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/accept_offline_v4_rotation.py"
SAMPLE = ROOT / "tests/test_offline_evidence_package_v2.py"


class OfflineV4CliAcceptanceTests(unittest.TestCase):
    def test_runner_and_dependency_sources_parse(self):
        for filename in (
            "scripts/accept_offline_v4_rotation.py",
            "scripts/offline_publisher_registry_v4.py",
            "scripts/offline_evidence_package_v3.py",
            "scripts/offline_evidence_package_v2.py",
        ):
            with self.subTest(filename=filename):
                path = ROOT / filename
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def test_cli_rotation_revocation_and_rollback(self):
        namespace = {}
        exec(compile(SAMPLE.read_text(encoding="utf-8"), str(SAMPLE), "exec"), namespace)
        # The fixture module only defines static synthetic receipt facts.
        receipt = namespace["receipt"]()
        import json
        with tempfile.TemporaryDirectory(prefix="afya-v4-accept-test-") as temp:
            source = Path(temp) / "synthetic-receipt.json"
            source.write_text(json.dumps(receipt), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--receipt", str(source)],
                cwd=ROOT, capture_output=True, text=True, timeout=100,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for marker in (
                "V4_CLI_ROTATION_ACCEPTANCE=PASS",
                "V4_INITIAL_PUBLISHER=PASS",
                "V4_REGISTRY_V2=PASS",
                "V4_REVOKED_OLD_KEY=BLOCKED_AS_EXPECTED",
                "V4_NEW_PUBLISHER_SIGNATURE=PASS",
                "V4_REGISTRY_ROLLBACK=BLOCKED_AS_EXPECTED",
                "V4_OLD_KEY_REVOCATION_FLOOR=PASS",
                "V4_DISPOSABLE_KEYS=REMOVED_AFTER_EXIT",
                "PRODUCTION_RELEASE=BLOCKED",
            ):
                self.assertIn(marker, result.stdout)

    def test_invalid_receipt_refused(self):
        with tempfile.TemporaryDirectory(prefix="afya-v4-refuse-") as temp:
            source = Path(temp) / "bad-receipt.json"
            source.write_text('{"data_mode":"zetaris"}', encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--receipt", str(source)],
                cwd=ROOT, capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("V4_CLI_ROTATION_ACCEPTANCE=FAIL", result.stdout)
            self.assertNotIn("V4_CLI_ROTATION_ACCEPTANCE=PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
