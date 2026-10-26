#!/usr/bin/env python3
"""Live Keycloak acceptance: no token or secret ever printed or persisted.

Requires a separately configured HTTPS Keycloak provider with three real
individual test accounts and the AfyaEvidence strict OIDC contract.
This is a read-only authentication/role test. No review decisions are written.
"""
import argparse
from getpass import getpass
import json
import os
from pathlib import Path
import sys

from afyaevidence.identity_auth import IdentityConfig, IdentityError, OIDCVerifier

EXPECT = {
    "viewer": {"read": True, "review": False, "recover": False},
    "reviewer": {"read": True, "review": True, "recover": False},
    "administrator": {"read": True, "review": False, "recover": True},
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity-config", type=Path, required=True)
    parser.add_argument("--noninteractive", action="store_true",
                        help="Only configuration preflight; do not request credentials")
    args = parser.parse_args(argv)
    try:
        conf = IdentityConfig.load(args.identity_config)
        secret = os.environ.get(conf.secret_env, "")
        if not secret:
            print("LIVE_KEYCLOAK=BLOCKED: introspection client secret environment variable unset")
            return 2
        verifier = OIDCVerifier(conf, secret)
        print("OIDC_CONFIGURATION=PASS")
        if args.noninteractive:
            print("LIVE_KEYCLOAK=NOT_TESTED: no user tokens provided")
            return 0
        actors = {}
        for role in EXPECT:
            token = getpass("Paste short-lived " + role + " test-account access token (hidden): ").strip()
            if not token:
                print("LIVE_KEYCLOAK=BLOCKED: missing test-account token")
                return 2
            try:
                principal = verifier.verify(token)
            except IdentityError as error:
                print("LIVE_KEYCLOAK=FAIL: " + role + " token rejected (" + error.code + ")")
                return 1
            if set(principal.roles) != {role}:
                print("LIVE_KEYCLOAK=FAIL: unexpected role set for " + role)
                return 1
            if principal.actor_id in actors:
                print("LIVE_KEYCLOAK=FAIL: distinct accounts required")
                return 1
            actors[principal.actor_id] = role
            for permission, expected in EXPECT[role].items():
                try:
                    principal.require(permission)
                    allowed = True
                except IdentityError:
                    allowed = False
                if allowed != expected:
                    print("LIVE_KEYCLOAK=FAIL: permission mismatch for " + role + "/" + permission)
                    return 1
            print("KEYCLOAK_ROLE_" + role.upper() + "=PASS")
        print("KEYCLOAK_DISTINCT_ACTORS=PASS")
        print("KEYCLOAK_ONLINE_INTROSPECTION=PASS")
        print("LIVE_KEYCLOAK=PASS")
        print("REVIEW_WRITE=NOT_RUN")
        print("REVOCATION_TEST=NOT_RUN")
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print("LIVE_KEYCLOAK=BLOCKED: configuration invalid or missing")
        return 2
    except (EOFError, KeyboardInterrupt):
        print("\nLIVE_KEYCLOAK=BLOCKED: operator cancelled")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
