"""Offline, sanitised Keycloak realm audit regression tests."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_keycloak_realm_exposure.py"
SPEC = importlib.util.spec_from_file_location("realm_audit", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

class RealmAuditTests(unittest.TestCase):
    def test_otp_flow_and_required_action_counts(self):
        realm = {"realm": "afya-local", "browserFlow": "browser", "loginTheme": "custom",
                 "otpPolicyType": "totp", "smtpServer": {"password": "NEVER_EXPORT"}}
        executions = [{"authenticator": "auth-otp-form", "requirement": "ALTERNATIVE"},
                      {"authenticator": "auth-username-password-form", "requirement": "REQUIRED"}]
        actions = [{"alias": "CONFIGURE_TOTP", "enabled": True, "defaultAction": False}]
        result = MOD.summarise(realm, executions, actions, [{"id": "hidden"}])
        encoded = json.dumps(result)
        self.assertEqual(result["otp_flow_executions"]["count"], 1)
        self.assertEqual(result["otp_required_action"]["enabled_count"], 1)
        self.assertEqual(result["themes"]["loginTheme"], "CONFIGURED")
        self.assertEqual(result["production_acceptance"], "BLOCKED")
        for secret in ("NEVER_EXPORT", "afya-local", "custom", "hidden"):
            self.assertNotIn(secret, encoded)

    def test_absent_input_is_not_claimed_verified(self):
        result = MOD.summarise({"realm": "afya-local"})
        self.assertEqual(result["otp_required_action"], "NOT_VERIFIED")
        self.assertEqual(result["otp_flow_executions"], "NOT_VERIFIED")
        self.assertEqual(result["component_provider_counts"], "NOT_VERIFIED")
        self.assertEqual(result["route_reachability"], "NOT_VERIFIED")

    def test_report_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp)
            realm = d / "realm.json"
            realm.write_text('{"realm":"afya-local","otpPolicyType":"totp"}')
            out = d / "report.json"
            cmd = [sys.executable, str(SCRIPT), "--realm", str(realm), "--report", str(out)]
            first = subprocess.run(cmd, text=True, capture_output=True, timeout=20)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(json.loads(out.read_text())["cve_2026_91415"], "OPEN")
            second = subprocess.run(cmd, text=True, capture_output=True, timeout=20)
            self.assertEqual(second.returncode, 2)
            self.assertIn("BLOCKED_REPORT_EXISTS", second.stdout)

if __name__ == "__main__":
    unittest.main()
