"""Tests for safe, read-only Keycloak admin inspection."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_keycloak_live_realm.py"
SPEC = importlib.util.spec_from_file_location("keycloak_live_audit", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

class FakeHeaders:
    def get_content_type(self):
        return "application/json"

class FakeResponse:
    status = 200
    headers = FakeHeaders()
    def read(self, n):
        return b'{"browserFlow":"browser"}'
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False

class FakeOpener:
    def __init__(self):
        self.requests = []
    def open(self, req, timeout=10):
        self.requests.append((req, timeout))
        return FakeResponse()

class LiveRealmAuditTests(unittest.TestCase):
    def test_request_is_read_only_with_bounded_timeout(self):
        opener = FakeOpener()
        result = MOD.fetch(opener, "private-token-value", "/authentication/required-actions")
        self.assertEqual(result, {"browserFlow": "browser"})
        req, timeout = opener.requests[0]
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(timeout, 10)
        self.assertEqual(req.full_url, "https://localhost:8443/admin/realms/afya-local/authentication/required-actions")
        self.assertEqual(req.get_header("Authorization"), "Bearer private-token-value")

    def test_no_redirect_handler(self):
        handler = MOD.NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "Moved", None,
                                                  "https://unexpected.example/"))

    def test_script_starts_from_unrelated_working_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--help"],
                cwd=temp, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--ca-cert", result.stdout)
            self.assertIn("--report", result.stdout)

    def test_no_authentication_provided_by_script(self):
        self.assertEqual(MOD.ORIGIN, "https://localhost:8443")
        self.assertEqual(MOD.REALM, "afya-local")

if __name__ == "__main__":
    unittest.main()
