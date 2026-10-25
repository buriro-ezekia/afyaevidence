"""Offline tests for Keycloak class constant-pool reverse-reference inspection."""
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_keycloak_java2d_reverse_refs.py"
SPEC = importlib.util.spec_from_file_location("keycloak_refs", SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)

def sample_class(*texts):
    encoded = b""
    for text in texts:
        value = text.encode("utf-8")
        encoded += bytes([1]) + struct.pack(">H", len(value)) + value
    return bytes.fromhex("cafebabe") + struct.pack(">HHH", 0, 65, len(texts) + 1) + encoded + bytes(8)

class KeycloakJava2DReverseReferenceTests(unittest.TestCase):
    def test_valid_class_constants(self):
        entries = AUDIT.utf8_constants(sample_class("java/awt/Font", "other/Thing"))
        self.assertEqual(entries, ["java/awt/Font", "other/Thing"])

    def test_invalid_class_cannot_be_accepted(self):
        with self.assertRaises(ValueError):
            AUDIT.utf8_constants(bytes.fromhex("cafebabe0000004100020100ff"))

    def test_font_and_zxing_references_with_no_reachability_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "main").mkdir()
            with zipfile.ZipFile(root / "main/example.jar", "w") as archive:
                archive.writestr("example/Reach.class", sample_class(
                    "org/locationtech/jts/awt/FontGlyphReader",
                    "com/google/zxing/client/j2se/MatrixToImageWriter"))
            result = AUDIT.scan(root)
            self.assertEqual(result["classes_scanned"], 1)
            self.assertEqual(result["target_counts"]["JTS_FONT_GLYPH"], 1)
            self.assertEqual(result["target_counts"]["ZXING_MATRIX_IMAGE"], 1)
            dest = root / "result.json"
            cmd = [sys.executable, str(SCRIPT), "--offline-directory",
                   str(root), "--report", str(dest)]
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            data = json.loads(dest.read_text())
            self.assertEqual(data["application_reachability"], "NOT_VERIFIED")
            self.assertEqual(data["container_release"], "BLOCKED")
            again = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            self.assertEqual(again.returncode, 2)
            self.assertIn("BLOCKED_REPORT_EXISTS", again.stdout)

    def test_missing_main_is_incomplete(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = AUDIT.scan(Path(temporary))
            self.assertIn("main_jars_missing", report["errors"])

if __name__ == "__main__":
    unittest.main()
