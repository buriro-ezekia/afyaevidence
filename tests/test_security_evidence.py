"""Pure security evidence checks; never need Docker, Keycloak or remote access."""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_security_evidence.py"
SPEC = importlib.util.spec_from_file_location("security_evidence", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

class SecurityEvidenceTests(unittest.TestCase):
    def test_high_critical_and_named_advisories_preserved(self):
        sample = {"Results": [
            {"Packages": [{"Name": "java-21-openjdk-headless"}],
             "Vulnerabilities": [
                 {"Severity": "CRITICAL", "VulnerabilityID": "CVE-2026-91403"},
                 {"Severity": "HIGH", "VulnerabilityID": "CVE-2026-91415"}]},
        ]}
        n, levels, tracked = MOD.analyse(sample)
        self.assertEqual(n, 1)
        self.assertEqual(levels["CRITICAL"], 1)
        self.assertEqual(levels["HIGH"], 1)
        self.assertEqual(tracked, MOD.TARGET)

    def test_missing_inventory_blocks(self):
        for report in ({}, {"Results": []}, {"Results": [{"Packages": []}]}):
            with self.subTest(report=report), self.assertRaises(ValueError):
                MOD.analyse(report)

    def test_missing_scan_gives_specific_reason_and_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            output = folder / "audit.json"
            command = [
                sys.executable, str(SCRIPT), "--trivy-report",
                str(folder / "absent-trivy.json"), "--out", str(output),
            ]
            result = subprocess.run(command, capture_output=True,
                                    text=True, timeout=15)
            self.assertEqual(result.returncode, 2)
            self.assertIn("SECURITY_AUDIT_REASON=trivy_report_not_found", result.stdout)
            self.assertIn("CONTAINER_RELEASE=BLOCKED", result.stdout)
            self.assertFalse(output.exists())

    def test_invalid_json_gives_specific_reason_and_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "trivy.json"
            source.write_text("{bad json", encoding="utf-8")
            output = folder / "audit.json"
            result = subprocess.run([
                sys.executable, str(SCRIPT), "--trivy-report",
                str(source), "--out", str(output),
            ], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 2)
            self.assertIn("SECURITY_AUDIT_REASON=invalid_trivy_json", result.stdout)
            self.assertFalse(output.exists())

    def test_absent_isolated_build_setuptools_does_not_block(self):
        from importlib.metadata import PackageNotFoundError
        versions = {"PyJWT": "2.13.0", "cryptography": "46.0.4"}
        def lookup(name):
            if name not in versions:
                raise PackageNotFoundError(name)
            return versions[name]
        installed, missing = MOD.dependency_inventory(lookup)
        self.assertEqual(missing, [])
        self.assertEqual(installed["setuptools"],
                         "NOT_INSTALLED_ISOLATED_BUILD_DEPENDENCY")

    def test_missing_runtime_dependency_remains_blocked(self):
        from importlib.metadata import PackageNotFoundError
        def lookup(name):
            if name == "PyJWT":
                raise PackageNotFoundError(name)
            return "46.0.4"
        installed, missing = MOD.dependency_inventory(lookup)
        self.assertEqual(missing, ["PyJWT"])
        self.assertEqual(installed["PyJWT"], "MISSING")

    def test_empty_advisories_do_not_imply_clearance(self):
        n, levels, tracked = MOD.analyse({
            "Results": [{"Packages": [{"Name": "other"}], "Vulnerabilities": []}]
        })
        self.assertEqual(n, 1)
        self.assertEqual(tracked, set())
        self.assertEqual(sum(levels.values()), 0)

if __name__ == "__main__":
    unittest.main()
