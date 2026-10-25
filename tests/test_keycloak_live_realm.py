"""Tests for safe, read-only Keycloak admin inspection."""
import importlib.util
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

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

    def test_unauthorised_http_status_has_safe_stage(self):
        class RejectingOpener:
            def open(self, request, timeout=10):
                raise HTTPError(request.full_url, 401, "private server text",
                                {"X-Internal": "private"}, None)
        with self.assertRaises(MOD.AdminAuditHTTPFailure) as caught:
            MOD.fetch_stage(RejectingOpener(), "very-private-admin-token",
                            "", "realm")
        self.assertEqual(caught.exception.status, 401)
        self.assertEqual(caught.exception.stage, "realm")
        self.assertNotIn("very-private-admin-token", str(caught.exception))
        self.assertNotIn("private server text", str(caught.exception))

    def test_forbidden_components_identifies_stage(self):
        class RejectingOpener:
            def open(self, request, timeout=10):
                raise HTTPError(request.full_url, 403, "private admin data", {}, None)
        with self.assertRaises(MOD.AdminAuditHTTPFailure) as caught:
            MOD.fetch_stage(RejectingOpener(), "private-token",
                            "/components", "components")
        self.assertEqual((caught.exception.stage, caught.exception.status),
                         ("components", 403))
        self.assertEqual(str(caught.exception), "admin_request_rejected")

    def test_invalid_audit_stage_rejected_before_request(self):
        class NoRequestOpener:
            def open(self, *args, **kwargs):
                self.fail("request must not occur")
        with self.assertRaises(ValueError):
            MOD.fetch_stage(NoRequestOpener(), "token", "/components", "other")

    def test_token_expiry_is_caught_before_admin_call(self):
        claims = {"iss": "https://localhost:8443/realms/master", "exp": 100}
        body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        token = "eyJhbGciOiJSUzI1NiJ9." + body + ".c2ln"
        self.assertEqual(MOD.token_preflight(token, now=101),
                         ("EXPIRED", "master", 0))
        self.assertEqual(MOD.token_preflight(token, now=90),
                         ("UNVERIFIED_ACTIVE_CLAIM", "master", 10))

    def test_token_prefix_and_missing_structure_fail_closed(self):
        self.assertEqual(MOD.token_preflight("Bearer a.b.c")[0],
                         "INVALID_PRESENTATION")
        self.assertEqual(MOD.token_preflight("no-jwt")[0], "INVALID_FORMAT")

    def test_no_authentication_provided_by_script(self):
        self.assertEqual(MOD.ORIGIN, "https://localhost:8443")
        self.assertEqual(MOD.REALM, "afya-local")

if __name__ == "__main__":
    unittest.main()
