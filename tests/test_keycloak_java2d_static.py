"""Pure offline regression checks for Keycloak Java 2D heuristic inventory."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_keycloak_java2d_static.py"
SPEC = importlib.util.spec_from_file_location("java2d_audit", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Java2DStaticAuditTests(unittest.TestCase):
    def test_class_marker_is_reported_but_not_exploitability(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "example.jar"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("org/example/SafeQr.class",
                           b"\xca\xfe\xba\xbe" + b"javax/imageio/ImageIO" + b"java/awt/image/BufferedImage")
                z.writestr("org/example/Plain.class", b"\xca\xfe\xba\xbe plain code")
            classes, skipped, matches = MODULE.scan_jar(archive)
            self.assertEqual((classes, skipped), (2, 0))
            self.assertEqual(len(matches), 1)
            self.assertIn("JAVA_IMAGEIO", matches[0]["markers"])
            self.assertIn("JAVA_AWT", matches[0]["markers"])

    def test_oversized_class_is_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "large.jar"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("example/TooLarge.class", b"java/awt/" + b"a" * 50)
            classes, skipped, matches = MODULE.scan_jar(archive, max_class_bytes=10)
            self.assertEqual((classes, skipped, matches), (1, 1, []))

    def test_invalid_jar_is_reported_in_incomplete_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            (tree / "invalid.jar").write_text("not a jar")
            data = MODULE.inspect_tree(tree)
            self.assertEqual(data["jars"], 1)
            self.assertEqual(len(data["failed_jars"]), 1)

    def test_offline_report_cannot_claim_production_clearance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = root / "main"
            main.mkdir()
            with zipfile.ZipFile(main / "example.jar", "w") as z:
                z.writestr("org/keycloak/example/Image.class", b"java/awt/image/BufferedImage")
            report = root / "security.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--offline-directory", str(root),
                 "--report", str(report)],
                capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(data["runtime_route_reachability"], "NOT_VERIFIED")
            self.assertEqual(data["production_acceptance"], "BLOCKED")
            self.assertIn("CVE_2026_91415=OPEN", result.stdout)
            again = subprocess.run(
                [sys.executable, str(SCRIPT), "--offline-directory", str(root),
                 "--report", str(report)],
                capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(again.returncode, 2)
            self.assertIn("JAVA2D_AUDIT=BLOCKED_REPORT_EXISTS", again.stdout)


if __name__ == "__main__":
    unittest.main()
