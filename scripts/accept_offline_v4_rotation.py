#!/usr/bin/env python3
"""Exercise real v2/v3/v4 CLIs with disposable keys and an existing synthetic receipt.

No original signing key, registry, review database or Keycloak state is read or
changed. Outputs are generated in a temporary owner-only directory and removed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SCRIPTS = Path(__file__).resolve().parent
V2 = SCRIPTS / "offline_evidence_package_v2.py"
V3 = SCRIPTS / "offline_evidence_package_v3.py"
V4 = SCRIPTS / "offline_publisher_registry_v4.py"


def execute(script, *args, expected=0, contains=()):
    command = [sys.executable, str(script), *map(str, args)]
    result = subprocess.run(command, cwd=SCRIPTS.parent, capture_output=True,
                            text=True, timeout=45, check=False)
    if result.returncode != expected or any(marker not in result.stdout for marker in contains):
        raise AssertionError(
            f"unexpected_command_outcome:{script.name}:exit={result.returncode}:"
            f"expected={expected}:stdout={result.stdout[-1500:]}:"
            f"stderr={result.stderr[-800:]}"
        )
    return result.stdout


def value(output, name):
    lines = [line.split("=", 1)[1] for line in output.splitlines()
             if line.startswith(name + "=")]
    if len(lines) != 1 or not lines[0]:
        raise AssertionError("missing_or_repeated_status:" + name)
    return lines[0]


def acceptance(receipt):
    if not receipt.is_file():
        raise ValueError("receipt_not_found")
    if not all(script.is_file() for script in (V2, V3, V4)):
        raise ValueError("missing_cli_script")
    if receipt.stat().st_size > 4_000_000:
        raise ValueError("oversized_receipt")

    # TemporaryDirectory is disposable; do not write secrets into project
    # runtime, or replace an existing accepted/previously signed package.
    with tempfile.TemporaryDirectory(prefix="afya-v4-rotation-") as temp:
        base = Path(temp)
        base.chmod(0o700)
        root_priv, root_pub = base / "root-private.pem", base / "root-public.pem"
        old_priv, old_pub = base / "old-private.pem", base / "old-public.pem"
        new_priv, new_pub = base / "new-private.pem", base / "new-public.pem"
        registry1, registry2 = base / "registry-v1.json", base / "registry-v2.json"
        package = base / "evidence.zip"
        signature1, signature2 = base / "old.sig.json", base / "new.sig.json"
        state_dir = base / "recipient-state"

        old_key = value(execute(V3, "keygen", "--private-key", old_priv,
                                "--public-key", old_pub,
                                contains=("OFFLINE_KEYGEN=PASS",)), "PUBLIC_KEY_ID")
        new_key = value(execute(V3, "keygen", "--private-key", new_priv,
                                "--public-key", new_pub,
                                contains=("OFFLINE_KEYGEN=PASS",)), "PUBLIC_KEY_ID")
        root_key = value(execute(V3, "keygen", "--private-key", root_priv,
                                 "--public-key", root_pub,
                                 contains=("OFFLINE_KEYGEN=PASS",)), "PUBLIC_KEY_ID")
        if len({root_key, old_key, new_key}) != 3:
            raise AssertionError("unexpected_duplicate_key")

        execute(V2, "create", "--receipt", receipt, "--output", package,
                "--valid-hours", "48", contains=("OFFLINE_PACKAGE=PASS",))
        execute(V2, "verify", "--package", package,
                contains=("OFFLINE_PACKAGE_INTEGRITY=PASS",
                          "OFFLINE_FRESHNESS=WITHIN_REVIEW_WINDOW"))
        execute(V4, "create-registry", "--root-private", root_priv,
                "--publisher-public", old_pub, "--publisher", "district_demo",
                "--version", "1", "--valid-hours", "48", "--output", registry1,
                contains=("TRUST_REGISTRY_CREATE=PASS", "REGISTRY_VERSION=1"))
        execute(V3, "sign", "--package", package, "--private-key", old_priv,
                "--signature", signature1,
                contains=("OFFLINE_PACKAGE_SIGNING=PASS",))
        common = ("--root-public", str(root_pub), "--state-dir", str(state_dir),
                  "--package", str(package))
        initial = execute(V4, "verify", *common, "--registry", registry1,
                          "--signature", signature1,
                          contains=("OFFLINE_V4_TRUST_REGISTRY=PASS",
                                    "TRUST_REGISTRY_VERSION=1",
                                    "PUBLISHER_KEY_STATUS=ACTIVE",
                                    "OFFLINE_PACKAGE_SIGNATURE=PASS"))
        if value(initial, "PUBLISHER_ID") != "district_demo":
            raise AssertionError("wrong_publisher_identity")
        if value(initial, "OFFLINE_FRESHNESS") != "WITHIN_REVIEW_WINDOW":
            raise AssertionError("stale_initial_evidence")

        execute(V4, "create-registry", "--root-private", root_priv,
                "--publisher-public", new_pub, "--publisher", "district_demo",
                "--version", "2", "--valid-hours", "48",
                "--previous-registry", registry1,
                "--revoke", old_key, "--output", registry2,
                contains=("TRUST_REGISTRY_CREATE=PASS", "REGISTRY_VERSION=2"))

        # A revoked key must be refused even if its old v3 signature is valid.
        execute(V4, "verify", *common, "--registry", registry2,
                              "--signature", signature1, expected=2,
                              contains=("OFFLINE_V4=BLOCKED_TRUST_OR_POLICY",))
        # The failed check pins the authenticated version-2 floor.
        floor = json.loads((state_dir / "last_registry.json").read_text())
        if floor.get("version") != 2 or old_key not in floor.get("revoked_key_ids", []):
            raise AssertionError("revocation_floor_not_recorded")

        execute(V3, "sign", "--package", package, "--private-key", new_priv,
                "--signature", signature2,
                contains=("OFFLINE_PACKAGE_SIGNING=PASS",))
        replacement = execute(V4, "verify", *common, "--registry", registry2,
                              "--signature", signature2,
                              contains=("OFFLINE_V4_TRUST_REGISTRY=PASS",
                                        "TRUST_REGISTRY_VERSION=2",
                                        "PUBLISHER_KEY_STATUS=ACTIVE",
                                        "OFFLINE_PACKAGE_SIGNATURE=PASS"))
        if value(replacement, "PUBLISHER_ID") != "district_demo":
            raise AssertionError("rotated_publisher_identity_mismatch")

        execute(V4, "verify", *common, "--registry", registry1,
                "--signature", signature1, expected=2,
                contains=("OFFLINE_V4=BLOCKED_TRUST_OR_POLICY",))
        # Prevent the suite from passing merely because an old key vanished.
        # A registry downgrade must be rejected even for a v2 signed package
        # that is still valid with the NEW key.
        execute(V4, "verify", *common, "--registry", registry1,
                "--signature", signature2, expected=2,
                contains=("OFFLINE_V4=BLOCKED_TRUST_OR_POLICY",))

        print("V4_CLI_ROTATION_ACCEPTANCE=PASS")
        print("V4_INITIAL_PUBLISHER=PASS")
        print("V4_REGISTRY_V2=PASS")
        print("V4_REVOKED_OLD_KEY=BLOCKED_AS_EXPECTED")
        print("V4_NEW_PUBLISHER_SIGNATURE=PASS")
        print("V4_REGISTRY_ROLLBACK=BLOCKED_AS_EXPECTED")
        print("V4_OLD_KEY_REVOCATION_FLOOR=PASS")
        print("V4_OFFLINE_REVIEW_SUBMISSION=DISABLED")
        print("PRODUCTION_RELEASE=BLOCKED")
    print("V4_DISPOSABLE_KEYS=REMOVED_AFTER_EXIT")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--receipt", type=Path, required=True,
                    help="Existing successful synthetic scripted receipt (read-only)")
    args = ap.parse_args()
    try:
        return acceptance(args.receipt.resolve())
    except (OSError, ValueError, AssertionError, subprocess.TimeoutExpired,
            json.JSONDecodeError) as error:
        print("V4_CLI_ROTATION_ACCEPTANCE=FAIL")
        print("V4_FAILURE=" + str(error)[:1800])
        print("PRODUCTION_RELEASE=BLOCKED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
