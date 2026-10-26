#!/usr/bin/env python3
"""Read-only HTTPS Keycloak admin inspection; never save tokens or raw realm data."""
from __future__ import annotations

import argparse
import base64
import time
import getpass
import json
from pathlib import Path
import ssl
import sys
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler, ProxyHandler

# Make the companion read-only summariser discoverable both when run as a
# script and when unittest loads this file directly via importlib.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from audit_keycloak_realm_exposure import summarise

ORIGIN = "https://localhost:8443"
REALM = "afya-local"

STAGES = ("realm", "browser_executions", "required_actions", "components")

def token_preflight(token: str, now: float | None = None):
    """Inspect local JWT metadata only; never mistake decoding for validation."""
    if token.lower().startswith("bearer ") or any(c.isspace() for c in token):
        return "INVALID_PRESENTATION", "UNKNOWN", 0
    try:
        parts = token.split(".")
        if len(parts) != 3 or not all(parts):
            return "INVALID_FORMAT", "UNKNOWN", 0
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        if not isinstance(data, dict):
            return "INVALID_FORMAT", "UNKNOWN", 0
        expiry = data.get("exp")
        issuer = data.get("iss")
        if (type(expiry) is not int or not isinstance(issuer, str) or
                not issuer.startswith("https://localhost:8443/realms/")):
            return "INVALID_CLAIMS", "UNKNOWN", 0
        realm = issuer.rsplit("/", 1)[-1]
        remaining = expiry - int(time.time() if now is None else now)
        if remaining <= 0:
            return "EXPIRED", realm, 0
        return "UNVERIFIED_ACTIVE_CLAIM", realm, remaining
    except (ValueError, IndexError, TypeError, UnicodeDecodeError):
        return "INVALID_FORMAT", "UNKNOWN", 0



class AdminAuditHTTPFailure(Exception):
    """Sanitised Keycloak admin response without raw URL, body or credentials."""
    def __init__(self, stage: str, status: int):
        self.stage = stage
        self.status = status
        super().__init__("admin_request_rejected")

def fetch_stage(opener, token: str, endpoint: str, stage: str):
    if stage not in STAGES:
        raise ValueError("invalid_audit_stage")
    try:
        return fetch(opener, token, endpoint)
    except HTTPError as exc:
        # HTTPError can carry a URL and body, neither of which is logged.
        raise AdminAuditHTTPFailure(stage, int(exc.code)) from None

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None

def fetch(opener, token: str, endpoint: str):
    url = ORIGIN + "/admin/realms/" + quote(REALM, safe="") + endpoint
    request = Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "Cache-Control": "no-store",
    }, method="GET")
    with opener.open(request, timeout=10) as response:
        if response.status != 200 or response.headers.get_content_type() != "application/json":
            raise ValueError("unexpected_admin_response")
        body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError("oversized_admin_response")
        return json.loads(body)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ca-cert", type=Path, required=True, help="Local explicitly trusted Keycloak TLS certificate")
    ap.add_argument("--report", type=Path, required=True, help="New sanitised JSON report; never overwrite")
    args = ap.parse_args()
    if args.report.exists():
        print("KEYCLOAK_LIVE_REALM_AUDIT=BLOCKED_REPORT_EXISTS")
        return 2
    if not args.ca_cert.is_file():
        print("KEYCLOAK_LIVE_REALM_AUDIT=BLOCKED_CA_CERT_MISSING")
        return 2
    token = getpass.getpass("Authorised Keycloak admin access token (hidden input): ").strip()
    if not token:
        print("KEYCLOAK_LIVE_REALM_AUDIT=BLOCKED_NO_TOKEN")
        return 2
    state, issuer_realm, remaining = token_preflight(token)
    print("TOKEN_PREFLIGHT=" + state)
    print("TOKEN_ISSUER_REALM=" + issuer_realm)
    print("TOKEN_REMAINING_SECONDS=" + str(remaining))
    print("TOKEN_SIGNATURE_VERIFIED=NO")
    if state != "UNVERIFIED_ACTIVE_CLAIM":
        print("KEYCLOAK_LIVE_REALM_AUDIT=BLOCKED_TOKEN_PREFLIGHT")
        print("REALM_EXPOSURE=NOT_VERIFIED")
        print("CONTAINER_RELEASE=BLOCKED")
        return 2
    try:
        context = ssl.create_default_context(cafile=str(args.ca_cert))
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())
        realm = fetch_stage(opener, token, "", "realm")
        if not isinstance(realm, dict):
            raise ValueError("invalid_realm_response")
        flow = realm.get("browserFlow")
        if not isinstance(flow, str) or not flow:
            raise ValueError("missing_browser_flow_alias")
        executions = fetch_stage(opener, token, "/authentication/flows/" + quote(flow, safe="") + "/executions", "browser_executions")
        actions = fetch_stage(opener, token, "/authentication/required-actions", "required_actions")
        components = fetch_stage(opener, token, "/components", "components")
        summary = summarise(realm, executions, actions, components)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, sort_keys=True)
            f.write("\n")
        print("KEYCLOAK_LIVE_REALM_AUDIT=PASS")
        print("OTP_ACTION_ENABLED_COUNT=" + str(summary["otp_required_action"]["enabled_count"]))
        print("OTP_ACTION_DEFAULT_COUNT=" + str(summary["otp_required_action"]["default_count"]))
        print("OTP_BROWSER_EXECUTION_COUNT=" + str(summary["otp_flow_executions"]["count"]))
        print("THEME_STATUS=" + json.dumps(summary["themes"], sort_keys=True))
        print("PROVIDER_COMPONENT_COUNT=" + str(summary["component_provider_counts"]["count"]))
        print("APPLICATION_REACHABILITY=NOT_VERIFIED")
        print("CVE_2026_91415=OPEN")
        print("CONTAINER_RELEASE=BLOCKED")
        print("REPORT=" + str(args.report))
        return 0
    except AdminAuditHTTPFailure as exc:
        print("KEYCLOAK_LIVE_REALM_AUDIT=BLOCKED_HTTPError")
        print("FAILED_STAGE=" + exc.stage)
        print("HTTP_STATUS=" + str(exc.status))
        if exc.status == 401:
            print("HTTP_DIAGNOSIS=TOKEN_EXPIRED_INVALID_OR_UNACCEPTED")
        elif exc.status == 403:
            print("HTTP_DIAGNOSIS=INSUFFICIENT_REALM_ADMIN_PERMISSIONS")
        elif exc.status == 404:
            print("HTTP_DIAGNOSIS=REALM_OR_ENDPOINT_NOT_FOUND")
        elif exc.status in (301, 302, 303, 307, 308):
            print("HTTP_DIAGNOSIS=UNEXPECTED_REDIRECT")
        else:
            print("HTTP_DIAGNOSIS=CHECK_KEYCLOAK_ADMIN_API")
        print("REALM_EXPOSURE=NOT_VERIFIED")
        print("CONTAINER_RELEASE=BLOCKED")
        return 2
    except Exception as exc:
        # Do not print exception bodies; URLs, token fragments or server data may leak.
        print("KEYCLOAK_LIVE_REALM_AUDIT=BLOCKED_" + type(exc).__name__)
        return 2

if __name__ == "__main__":
    sys.exit(main())
