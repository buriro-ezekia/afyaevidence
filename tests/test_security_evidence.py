"""Pure security evidence checks; never need Docker, Keycloak or remote access."""
import importlib.util
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

    def test_empty_advisories_do_not_imply_clearance(self):
        n, levels, tracked = MOD.analyse({
            "Results": [{"Packages": [{"Name": "other"}], "Vulnerabilities": []}]
        })
        self.assertEqual(n, 1)
        self.assertEqual(tracked, set())
        self.assertEqual(sum(levels.values()), 0)

if __name__ == "__main__":
    unittest.main()
