#!/usr/bin/env python3
"""Safely summarise a local Keycloak realm export for OpenJDK 2D exposure review.

This never connects to Keycloak. Input JSON stays local and is never copied
into output. The summary contains only selected flow/OTP/theme/provider facts.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

OTP_TOKENS = ("otp", "totp", "configure-totp", "auth-otp-form")
THEME_KEYS = ("loginTheme", "accountTheme", "emailTheme", "adminTheme")
MAX_BYTES = 8_000_000

def load(path: Path):
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("oversized_input")
    return json.loads(path.read_text(encoding="utf-8"))

def summarise(realm, executions=None, actions=None, components=None):
    if not isinstance(realm, dict):
        raise ValueError("invalid_realm")
    report = {
        "realm_id": "REDACTED",
        "configuration_source": "operator_export",
        "otp_policy_present": isinstance(realm.get("otpPolicyType"), str),
        "otp_required_action": "NOT_VERIFIED",
        "otp_flow_executions": "NOT_VERIFIED",
        "browser_flow_alias_present": bool(realm.get("browserFlow")),
        "themes": {key: ("CONFIGURED" if realm.get(key) else "DEFAULT_OR_UNSPECIFIED")
                   for key in THEME_KEYS},
        "component_provider_counts": "NOT_VERIFIED",
        "route_reachability": "NOT_VERIFIED",
        "cve_2026_91415": "OPEN",
        "production_acceptance": "BLOCKED",
    }
    if actions is not None:
        if not isinstance(actions, list):
            raise ValueError("invalid_required_actions")
        otp = [x for x in actions if isinstance(x, dict) and
               any(token in str(x.get("alias", "")).lower() for token in OTP_TOKENS)]
        report["otp_required_action"] = {
            "count": len(otp),
            "enabled_count": sum(x.get("enabled") is True for x in otp),
            "default_count": sum(x.get("defaultAction") is True for x in otp),
        }
    if executions is not None:
        if not isinstance(executions, list):
            raise ValueError("invalid_executions")
        otp = [x for x in executions if isinstance(x, dict) and
               any(token in str(x.get("authenticator", "")).lower()
                   or token in str(x.get("displayName", "")).lower()
                   for token in OTP_TOKENS)]
        report["otp_flow_executions"] = {
            "count": len(otp),
            "requirement_counts": dict(Counter(str(x.get("requirement", "UNKNOWN"))
                                               for x in otp)),
        }
    if components is not None:
        if not isinstance(components, list):
            raise ValueError("invalid_components")
        # Do not disclose provider names, component IDs or credentials.
        report["component_provider_counts"] = {"count": len(components)}
    return report

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--realm", type=Path, required=True)
    ap.add_argument("--executions", type=Path)
    ap.add_argument("--required-actions", type=Path)
    ap.add_argument("--components", type=Path)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    if args.report.exists():
        print("REALM_EXPOSURE_AUDIT=BLOCKED_REPORT_EXISTS")
        return 2
    try:
        inputs = [args.realm, args.executions, args.required_actions, args.components]
        for p in filter(None, inputs):
            if not p.is_file():
                raise ValueError("input_missing")
        result = summarise(load(args.realm), *(load(x) if x else None for x in inputs[1:]))
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as f:
            json.dump(result, f, indent=2, sort_keys=True)
            f.write("\n")
        print("REALM_EXPOSURE_AUDIT=PASS")
        print("OTP_REQUIRED_ACTION=" + ("NOT_VERIFIED" if isinstance(result["otp_required_action"], str)
              else str(result["otp_required_action"]["enabled_count"]) + "_ENABLED"))
        print("OTP_FLOW_EXECUTIONS=" + ("NOT_VERIFIED" if isinstance(result["otp_flow_executions"], str)
              else str(result["otp_flow_executions"]["count"])))
        print("THEMES=" + json.dumps(result["themes"], sort_keys=True))
        print("COMPONENTS=" + ("NOT_VERIFIED" if isinstance(result["component_provider_counts"], str)
              else str(result["component_provider_counts"]["count"])))
        print("APPLICATION_REACHABILITY=NOT_VERIFIED")
        print("CVE_2026_91415=OPEN")
        print("CONTAINER_RELEASE=BLOCKED")
        print("REPORT=" + str(args.report))
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print("REALM_EXPOSURE_AUDIT=BLOCKED_" + type(exc).__name__)
        return 2

if __name__ == "__main__":
    sys.exit(main())
