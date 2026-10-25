#!/usr/bin/env python3
"""Read-only HTTPS Keycloak admin inspection; never save tokens or raw realm data."""
from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
import ssl
import sys
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
    try:
        context = ssl.create_default_context(cafile=str(args.ca_cert))
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())
        realm = fetch(opener, token, "")
        if not isinstance(realm, dict):
            raise ValueError("invalid_realm_response")
        flow = realm.get("browserFlow")
        if not isinstance(flow, str) or not flow:
            raise ValueError("missing_browser_flow_alias")
        executions = fetch(opener, token, "/authentication/flows/" + quote(flow, safe="") + "/executions")
        actions = fetch(opener, token, "/authentication/required-actions")
        components = fetch(opener, token, "/components")
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
    except Exception as exc:
        # Do not print exception bodies; URLs, token fragments or server data may leak.
        print("KEYCLOAK_LIVE_REALM_AUDIT=BLOCKED_" + type(exc).__name__)
        return 2

if __name__ == "__main__":
    sys.exit(main())
