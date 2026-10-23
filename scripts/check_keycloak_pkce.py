#!/usr/bin/env python3
"""One real human Keycloak login using OAuth2 authorization code + PKCE S256.

Requires a configured Keycloak public PKCE client and a confidential
introspection client. Does not persist or print access/refresh tokens.
This is an authentication smoke test, not a review-write test.
"""
from __future__ import annotations

import argparse
import base64
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import ssl
import sys
from urllib.error import URLError, HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, HTTPSHandler, ProxyHandler, build_opener

from afyaevidence.identity_auth import IdentityConfig, IdentityError, OIDCVerifier, ProviderTransport


class DiagnosticTransport(ProviderTransport):
    """Reports only comparison booleans, never tokens or claim values."""
    def __init__(self):
        super().__init__()
        self.jwks_reached = False
        self.introspection_reached = False
        self.status = {}

    def json(self, url, *, body=None, headers=None):
        doc = super().json(url, body=body, headers=headers)
        if body is None:
            self.jwks_reached = True
        else:
            self.introspection_reached = True
            # Diagnostics compare claims, without printing personal data or secrets.
            claim = getattr(self, "untrusted_claim", {})
            self.status = {
                "active": doc.get("active") is True,
                "iss_present": isinstance(doc.get("iss"), str),
                "iss_equal": doc.get("iss") == claim.get("iss"),
                "aud_present": "aud" in doc,
                "aud_equal": doc.get("aud") == claim.get("aud"),
                "sub_present": isinstance(doc.get("sub"), str),
                "sub_equal": doc.get("sub") == claim.get("sub"),
                "exp_present": type(doc.get("exp")) is int,
                "exp_equal": doc.get("exp") == claim.get("exp")
            }
        return doc


def token_structure(token, transport, conf):
    # This is an UNVERIFIED hint only; never use it to grant permission.
    try:
        parts = token.split(".")
        if len(parts) != 3: return {"jwt_shape": False}
        header = json.loads(base64.urlsafe_b64decode(parts[0] + "=" * (-len(parts[0]) % 4)))
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        if not isinstance(header, dict) or not isinstance(claims, dict): return {"jwt_shape": False}
        transport.untrusted_claim = claims
        return {
            "jwt_shape": True,
            "header_alg_rs256": header.get("alg") == "RS256",
            "header_typ_at_jwt": header.get("typ") == "at+jwt",
            "kid_present": isinstance(header.get("kid"), str),
            "issuer_match_unverified": claims.get("iss") == conf.issuer,
            "audience_match_unverified": claims.get("aud") == conf.audience and type(claims.get("aud")) is str,
            "roles_list_unverified": isinstance(claims.get(conf.roles_claim), list),
            "required_claims_present_unverified": all(k in claims for k in ("sub","jti","iat","nbf","exp")),
            "claim_sub_present_unverified": isinstance(claims.get("sub"), str) and bool(claims.get("sub")),
            "claim_jti_present_unverified": isinstance(claims.get("jti"), str) and bool(claims.get("jti")),
            "claim_iat_integer_unverified": type(claims.get("iat")) is int,
            "claim_nbf_integer_unverified": type(claims.get("nbf")) is int,
            "claim_exp_integer_unverified": type(claims.get("exp")) is int,
        }
    except (ValueError, TypeError, UnicodeError, KeyError):
        return {"jwt_shape": False}


def report_diagnostics(structure, transport):
    print("PKCE_DIAGNOSTIC=UNVERIFIED_FLAGS_ONLY")
    for key, val in structure.items():
        print("TOKEN_" + key.upper() + "=" + ("YES" if val else "NO"))
    print("JWKS_FETCHED=" + ("YES" if transport.jwks_reached else "NO"))
    print("INTROSPECTION_REACHED=" + ("YES" if transport.introspection_reached else "NO"))
    for key, val in transport.status.items():
        print("INTROSPECTION_" + key.upper() + "=" + ("YES" if val else "NO"))


def live_http_role_test(role, token, principal, port=8011):
    """One isolated test against loopback port 8011; no token ever logged."""
    from urllib.request import HTTPHandler
    base = f"http://127.0.0.1:{port}/api/runs/run_pending"
    opener = build_opener(ProxyHandler({}), HTTPHandler())

    def call(method, url, data=None):
        headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = Request(url, method=method, headers=headers, data=data)
        try:
            with opener.open(req, timeout=10) as response:
                raw = response.read(262145)
                if len(raw)>262144:
                    raise ValueError("oversized_response")
                return response.status, json.loads(raw)
        except HTTPError as exc:
            # Only inspect stable allowlisted application error identifiers;
            # never print arbitrary bodies, URLs, tokens or personal data.
            safe_codes = {"identity_provider_unavailable", "storage_unavailable",
                          "operation_unavailable", "unauthorised", "forbidden",
                          "unknown_run", "not_found"}
            try:
                raw_error = exc.read(2048)
                parsed = json.loads(raw_error)
                code = parsed.get("error") if isinstance(parsed, dict) else None
            except (ValueError, UnicodeError, OSError, TypeError):
                code = None
            return exc.code, {"safe_error": code if code in safe_codes else "unclassified"}

    try:
        before_code, before = call("GET", base)
        if before_code != 200 or not isinstance(before, dict):
            print("LIVE_HTTP_GET_STATUS=" + str(before_code))
            print("LIVE_HTTP_GET_ERROR=" + str(before.get("safe_error", "unclassified")))
            # Only a small allowlist of stable server error codes is reported.
            # Never print request headers, JWTs, private identifiers or response bodies.
            print("LIVE_HTTP_ROLE=FAIL: authenticated evidence read failed")
            return 1
        if before.get("revision") != 0 or before.get("disposition") is not None:
            print("LIVE_HTTP_ROLE=BLOCKED: run_pending is no longer unreviewed")
            return 2
        print("LIVE_HTTP_EVIDENCE_READ=PASS")
        payload = json.dumps({
            "expected_revision": 0,
            "event_key": "live_" + role + "_" + secrets.token_hex(12),
            "disposition": "request_more_evidence",
            "reason": "Synthetic identity HTTP acceptance; more evidence required.",
        }).encode("utf-8")
        post_code, outcome = call("POST", base + "/reviews", payload)
        if role != "reviewer":
            after_code, after = call("GET", base)
            if (post_code != 403 or after_code != 200
                    or after.get("revision") != 0 or after.get("disposition") is not None
                    or after.get("history") != before.get("history")):
                print("LIVE_HTTP_ROLE=FAIL: denial or immutability mismatch")
                return 1
            print("LIVE_HTTP_" + role.upper() + "_WRITE_DENIED=PASS")
            print("LIVE_HTTP_REVIEW_STATE_UNCHANGED=PASS")
            print("LIVE_HTTP_ROLE=PASS")
            return 0
        after_code, after = call("GET", base)
        history = after.get("history", []) if isinstance(after, dict) else []
        final = history[-1] if history else {}
        who = final.get("identity", {}) if isinstance(final, dict) else {}
        if (post_code != 200 or outcome.get("revision") != 1 or outcome.get("replayed") is not False
                or after_code != 200 or after.get("revision") != 1
                or after.get("disposition") != "request_more_evidence"
                or len(history) != 1 or final.get("disposition") != "request_more_evidence"
                or who.get("kind") != "verified_oidc" or who.get("issuer") != principal.issuer
                or who.get("subject") != principal.subject or "reviewer" not in who.get("roles", [])):
            print("LIVE_HTTP_ROLE=FAIL: reviewer write/audit mismatch")
            return 1
        print("LIVE_HTTP_REVIEWER_WRITE=PASS")
        print("LIVE_HTTP_VERIFIED_AUDIT=PASS")
        print("LIVE_HTTP_ROLE=PASS")
        return 0
    except (OSError, URLError, ValueError, TypeError, KeyError):
        print("LIVE_HTTP_ROLE=FAIL: API unavailable or unexpected response")
        return 1


def live_provider_outage_test(token, port):
    """Read-only fail-closed check with bounded automatic Keycloak recovery.

    The token stays in memory. No health records, tokens, passwords, environment
    values or HTTP bodies are logged or persisted.
    """
    import subprocess
    import time
    from urllib.request import HTTPHandler

    name = "afyaevidence-keycloak-local"
    endpoint = f"http://127.0.0.1:{port}/api/runs/run_pending"
    opener = build_opener(ProxyHandler({}), HTTPHandler())

    def api_read():
        request = Request(endpoint, headers={
            "Authorization": "Bearer " + token, "Accept": "application/json"},
            method="GET")
        try:
            with opener.open(request, timeout=9) as response:
                return response.status
        except HTTPError as exc:
            return exc.code
        except (OSError, URLError):
            return 0

    def docker(*args, timeout=60):
        return subprocess.run(["docker", *args], check=False, timeout=timeout,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode

    before = api_read()
    if before != 200:
        print("OUTAGE_BASELINE_HTTP=" + str(before))
        print("AUTHENTICATED_OUTAGE=BLOCKED")
        return 2

    # Refuse to modify an unexpected Docker container or unavailable daemon.
    try:
        check = subprocess.run(
            ["docker", "inspect", "--format", "{{.Config.Image}}|{{.State.Running}}", name],
            check=False, capture_output=True, text=True, timeout=10)
        fields = check.stdout.strip().split("|")
        if (check.returncode != 0 or len(fields) != 2
                or not fields[0].startswith("quay.io/keycloak/keycloak:")
                or fields[1] != "true"):
            print("KEYCLOAK_CONTAINER_PREFLIGHT=BLOCKED")
            return 2
    except (OSError, subprocess.TimeoutExpired):
        print("KEYCLOAK_CONTAINER_PREFLIGHT=BLOCKED")
        return 2

    started_stop = False
    status = 2
    recovered = False
    try:
        # Mark before stopping so even Ctrl+C or Docker timeout enters recovery.
        started_stop = True
        if docker("stop", "--time", "12", name, timeout=30) != 0:
            print("KEYCLOAK_OUTAGE_STOP=FAIL")
        else:
            print("KEYCLOAK_OUTAGE_STOP=PASS")
            during = api_read()
            print("AUTHENTICATED_OUTAGE_HTTP=" + str(during))
            if during == 503:
                print("AUTHENTICATED_FAIL_CLOSED=PASS")
                status = 0
            else:
                print("AUTHENTICATED_FAIL_CLOSED=FAIL")
                status = 1
    except (OSError, subprocess.TimeoutExpired):
        print("AUTHENTICATED_OUTAGE=BLOCKED: Docker interruption failed")
    finally:
        if started_stop:
            try:
                if docker("start", name, timeout=45) == 0:
                    from urllib.request import HTTPSHandler
                    cert = Path.home()/".local/state/afyaevidence-keycloak-local/tls/tls.crt"
                    tls = ssl.create_default_context(cafile=str(cert))
                    secure = build_opener(ProxyHandler({}), HTTPSHandler(context=tls))
                    discovery = AUTHORITY + "/.well-known/openid-configuration"
                    deadline = time.monotonic() + 90
                    while time.monotonic() < deadline:
                        try:
                            with secure.open(discovery, timeout=4) as response:
                                if response.status == 200:
                                    recovered = True
                                    break
                        except (OSError, URLError, HTTPError):
                            pass
                        time.sleep(2)
                print("KEYCLOAK_RECOVERY=" + ("PASS" if recovered else "FAIL"))
            except (OSError, ValueError, subprocess.TimeoutExpired):
                print("KEYCLOAK_RECOVERY=FAIL")

    if not recovered:
        print("AUTHENTICATED_OUTAGE=INCOMPLETE_RECOVERY")
        return 2
    if status == 0:
        print("AUTHENTICATED_OUTAGE=PASS")
    print("REVIEW_WRITE=NOT_RUN")
    print("REVOCATION=NOT_TESTED")
    return status



def live_revocation_test(token, refresh_token, port, opener):
    """End only the fresh viewer session, then read API with same access token.

    Does not print tokens/refresh tokens or change review records. Fail
    closed if Keycloak cannot confirm logout or if HTTP still grants access.
    """
    from urllib.request import HTTPHandler
    import time
    if not isinstance(refresh_token, str) or not refresh_token:
        print("REVOCATION=BLOCKED: refresh token unavailable")
        return 2
    endpoint = f"http://127.0.0.1:{port}/api/runs/run_pending"
    local = build_opener(ProxyHandler({}), HTTPHandler())

    def read():
        req = Request(endpoint, method="GET",
                      headers={"Authorization":"Bearer " + token, "Accept":"application/json"})
        try:
            with local.open(req, timeout=9) as response:
                return response.status
        except HTTPError as error:
            return error.code
        except (OSError, URLError):
            return 0

    before = read()
    print("REVOCATION_PRE_HTTP=" + str(before))
    if before != 200:
        print("REVOCATION=BLOCKED: no valid authenticated baseline")
        return 2

    logout_url = AUTHORITY + "/protocol/openid-connect/logout"
    body = urlencode({"client_id":"afya-human-login",
                      "refresh_token":refresh_token}).encode()
    request = Request(logout_url, data=body, method="POST",
                      headers={"Content-Type":"application/x-www-form-urlencoded"})
    try:
        with opener.open(request, timeout=10) as response:
            if response.status not in (200, 204):
                raise ValueError("logout_status")
    except (HTTPError, URLError, OSError, ValueError):
        print("KEYCLOAK_SESSION_LOGOUT=FAIL")
        print("REVOCATION=BLOCKED")
        return 2

    print("KEYCLOAK_SESSION_LOGOUT=PASS")
    # Keycloak session invalidation should be immediately observable by
    # mandatory introspection. Allow a small propagation window, never
    # treating an initial HTTP 200 as success.
    seen = None
    deadline = time.monotonic() + 8
    while True:
        seen = read()
        if seen == 401 or time.monotonic() >= deadline:
            break
        time.sleep(0.5)
    print("REVOCATION_POST_HTTP=" + str(seen))
    if seen == 401:
        print("LIVE_REVOCATION=PASS")
        print("REVIEW_WRITE=NOT_RUN")
        return 0
    print("LIVE_REVOCATION=FAIL")
    return 1


AUTHORITY = "https://localhost:8443/realms/afya-local"
CALLBACK = "http://127.0.0.1:8765/callback"
ALLOWED = frozenset(("viewer", "reviewer", "administrator"))


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity-config", type=Path, required=True)
    parser.add_argument("--role", required=True, choices=sorted(ALLOWED))
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--http-role-test", action="store_true",
                        help="Test HTTP read/write against isolated run_pending")
    parser.add_argument("--revocation-test", action="store_true",
                        help="Logout a fresh viewer session then require API 401 for the same token")
    parser.add_argument("--authenticated-outage-test", action="store_true",
                        help="Read-only live outage: stop isolated Keycloak and always attempt restart")
    parser.add_argument("--http-port", type=int, default=8011,
                        help="Loopback identity-review server port (default 8011)")
    args = parser.parse_args(argv)

    if args.revocation_test and (args.http_role_test or args.authenticated_outage_test or args.role != "viewer"):
        parser.error("revocation test requires --role viewer and excludes other test modes")
    if args.authenticated_outage_test and (args.http_role_test or args.role != "viewer"):
        parser.error("outage test requires --role viewer and excludes --http-role-test")
    if not 1024 <= args.http_port <= 65535:
        parser.error("HTTP port must be 1024-65535")
    if not 30 <= args.timeout_seconds <= 600:
        parser.error("timeout must be between 30 and 600 seconds")
    try:
        conf = IdentityConfig.load(args.identity_config)
        if conf.issuer != AUTHORITY:
            print("PKCE_LOGIN=BLOCKED: issuer differs from local test realm")
            return 2
        secret = os.environ.get(conf.secret_env)
        if not secret:
            print("PKCE_LOGIN=BLOCKED: introspection secret is not configured")
            return 2
        diagnostic_transport = DiagnosticTransport()
        verifier = OIDCVerifier(conf, secret, transport=diagnostic_transport)
        cert = Path.home() / ".local/state/afyaevidence-keycloak-local/tls/tls.crt"
        if not cert.is_file():
            print("PKCE_LOGIN=BLOCKED: trusted local CA missing")
            return 2
        ssl_ctx = ssl.create_default_context(cafile=str(cert))
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl_ctx))
    except (ValueError, OSError, TypeError):
        print("PKCE_LOGIN=BLOCKED: invalid private identity configuration")
        return 2

    state = secrets.token_urlsafe(32)
    verifier_secret = b64(secrets.token_bytes(32))
    challenge = b64(sha256(verifier_secret.encode("ascii")).digest())
    result = {"code": None, "error": None}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass  # Prevent query parameters (authorization codes) entering logs.

        def do_GET(self):
            host = self.headers.get("Host")
            path = urlsplit(self.path)
            fields = parse_qs(path.query, keep_blank_values=True)
            good = (host == "127.0.0.1:8765" and path.path == "/callback"
                    and not path.fragment and not path.scheme and not path.netloc
                    and len(self.path) < 8192 and fields.get("state") == [state])
            if not good or any(len(v) != 1 for v in fields.values()):
                self._send(400, "Login callback rejected. Return to the terminal.")
                return
            if "error" in fields:
                result["error"] = "authorization_denied"
                self._send(400, "Login was not authorised. Return to the terminal.")
                return
            code = fields.get("code", [None])[0]
            if not code or len(code) > 4096 or result["code"]:
                self._send(400, "Invalid or repeated authorization response.")
                return
            result["code"] = code
            self._send(200, "Keycloak browser sign-in received. Return to your terminal.")

        def _send(self, status, message):
            payload = message.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    try:
        server = HTTPServer(("127.0.0.1", 8765), Callback)
    except OSError:
        print("PKCE_LOGIN=BLOCKED: localhost callback port 8765 unavailable")
        return 2
    server.timeout = 1
    params = {
        "response_type": "code",
        "client_id": "afya-human-login",
        "redirect_uri": CALLBACK,
        "scope": "openid",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "login",
        "max_age": "0",
    }
    auth_url = AUTHORITY + "/protocol/openid-connect/auth?" + urlencode(params)
    print("PKCE_BROWSER_LOGIN=READY")
    print("Use a fresh private/incognito browser window to avoid a previous test account session.")
    print("Sign in only as an individual account with the " + args.role + " role.")
    print("Open this URL on the same computer (do not share it or put it in GitHub):")
    print(auth_url)
    try:
        import time
        deadline = time.monotonic() + args.timeout_seconds
        while time.monotonic() < deadline and result["code"] is None and result["error"] is None:
            server.handle_request()
    except KeyboardInterrupt:
        print("\nPKCE_LOGIN=BLOCKED: cancelled")
        return 2
    finally:
        server.server_close()
    if result["error"]:
        print("PKCE_LOGIN=FAIL: authorization rejected")
        return 1
    if not result["code"]:
        print("PKCE_LOGIN=BLOCKED: no valid callback received")
        return 2

    token_request = Request(
        AUTHORITY + "/protocol/openid-connect/token",
        data=urlencode({
            "grant_type": "authorization_code",
            "client_id": "afya-human-login",
            "redirect_uri": CALLBACK,
            "code": result["code"],
            "code_verifier": verifier_secret,
        }).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"},
        method="POST")
    try:
        with opener.open(token_request, timeout=10) as response:
            if response.status != 200 or response.headers.get_content_type() != "application/json":
                raise ValueError("unexpected token response")
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError("token response too large")
        doc = json.loads(raw)
        token = doc.get("access_token")
        if not isinstance(token, str) or not token:
            raise ValueError("access token missing")
        structure = token_structure(token, diagnostic_transport, conf)
        principal = verifier.verify(token)
    except IdentityError as err:
        print("PKCE_LOGIN=FAIL: " + err.code)
        report_diagnostics(locals().get("structure", {}), diagnostic_transport)
        print("Check header typ, issuer, exact audience, flat roles and introspection claim compatibility.")
        return 1
    except (HTTPError, URLError, ValueError, KeyError, TypeError, OSError):
        print("PKCE_LOGIN=FAIL: token exchange or provider verification unavailable")
        return 1

    if set(principal.roles) != {args.role}:
        print("PKCE_LOGIN=FAIL: unexpected application roles")
        # These booleans describe only the three public application role names;
        # never print JWTs, identity claims or complete principal objects.
        for role in ("viewer", "reviewer", "administrator"):
            print("VERIFIED_ROLE_" + role.upper() + "=" +
                  ("YES" if role in principal.roles else "NO"))
        print("EXPECTED_ROLE_" + args.role.upper() + "=YES")
        print("LIVE_SIGNATURE_AND_INTROSPECTION=PASS")
        return 1
    expected = {"read": True, "review": args.role == "reviewer",
                "recover": args.role == "administrator"}
    for permission, allowed in expected.items():
        try:
            principal.require(permission)
            actual = True
        except IdentityError:
            actual = False
        if actual != allowed:
            print("PKCE_LOGIN=FAIL: permission mismatch for " + permission)
            return 1
    print("PKCE_AUTHORIZATION_CODE=PASS")
    print("PKCE_SIGNED_ACCESS_TOKEN=PASS")
    print("PKCE_ONLINE_INTROSPECTION=PASS")
    print("PKCE_ROLE_" + args.role.upper() + "=PASS")
    print("PKCE_LOGIN=PASS")
    if args.revocation_test:
        return live_revocation_test(token, doc.get("refresh_token"), args.http_port, opener)
    if args.authenticated_outage_test:
        return live_provider_outage_test(token, args.http_port)
    if args.http_role_test:
        status = live_http_role_test(args.role, token, principal, port=args.http_port)
        print("REVOCATION=NOT_TESTED")
        return status
    print("REVIEW_WRITE=NOT_RUN")
    print("REVOCATION=NOT_TESTED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
