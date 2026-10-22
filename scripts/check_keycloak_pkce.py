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
    args = parser.parse_args(argv)

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
    print("REVIEW_WRITE=NOT_RUN")
    print("REVOCATION=NOT_TESTED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
