#!/usr/bin/env python3
"""Read-only completeness audit: source, tests, docs and release evidence.

The audit distinguishes structural presence from tests actually run and
operator evidence. It never certifies clinical safety or production security.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

FILES = {
    "agent": ["src/afyaevidence/agent.py", "src/afyaevidence/agent_cli.py"],
    "data": ["src/afyaevidence/jdbc.py", "src/afyaevidence/snapshot.py"],
    "memory": ["src/afyaevidence/memory.py"],
    "review": ["src/afyaevidence/review_server.py", "src/afyaevidence/identity_review_server.py"],
    "authorisation": ["src/afyaevidence/identity_auth.py", "src/afyaevidence/identity_store.py"],
    "worker": ["src/afyaevidence/managed_worker.py", "src/afyaevidence/managed_entry.py"],
    "test_harness": ["scripts/verify_identity_worker.py", "scripts/check_managed_systemd.py",
                     "scripts/check_keycloak_pkce.py"],
}
DOCUMENTS = ["README.md", "docs/IDENTITY_WORKER_IMPLEMENTATION.md",
             "docs/KEYCLOAK_LIVE_ACCEPTANCE.md",
             "docs/KEYCLOAK_HTTP_ROLE_ACCEPTANCE.md",
             "docs/KEYCLOAK_AUTHENTICATED_OUTAGE_TEST.md",
             "docs/KEYCLOAK_SESSION_REVOCATION_TEST.md",
             "docs/KEYCLOAK_RESIDUAL_SECURITY.md",
             "docs/KEYCLOAK_JAVA2D_APPLICABILITY.md",
             "scripts/audit_keycloak_java2d_reverse_refs.py",
             "tests/test_keycloak_java2d_reverse_refs.py",
             "scripts/audit_keycloak_realm_exposure.py",
             "tests/test_keycloak_realm_exposure.py",
             "scripts/audit_keycloak_live_realm.py",
             "tests/test_keycloak_live_realm.py",
             "scripts/audit_keycloak_container_extensions.py",
             "tests/test_keycloak_container_extensions.py",
             "scripts/export_offline_briefcase.py",
             "tests/test_offline_briefcase.py",
             "docs/OFFLINE_EVIDENCE_BRIEFCASE.md",
             "scripts/offline_evidence_package_v2.py",
             "tests/test_offline_evidence_package_v2.py",
             "docs/OFFLINE_EVIDENCE_PACKAGES_V2.md",
             "scripts/offline_evidence_package_v3.py",
             "tests/test_offline_evidence_package_v3.py",
             "docs/OFFLINE_EVIDENCE_PACKAGES_V3.md",
             "scripts/offline_publisher_registry_v4.py",
             "tests/test_offline_publisher_registry_v4.py",
             "docs/OFFLINE_EVIDENCE_PACKAGES_V4.md",
             "scripts/accept_offline_v4_rotation.py",
             "tests/test_offline_v4_cli_rotation.py",
             "docs/OFFLINE_V4_ROTATION_ACCEPTANCE.md",
             "docs/CI_AND_SECURITY_READINESS.md",
             "scripts/audit_security_evidence.py",
             "tests/test_security_evidence.py"]
RELEASE_GATES = {
    "independent_security_review": "PENDING",
    "hosted_ci": "FAILED_PRE_RUNNER_UNRESOLVED",
    "keycloak_container_security": "BLOCKED_BY_REPORTED_CVES",
    "deployment_tls": "NOT_VERIFIED",
    "dedicated_service_account": "NOT_VERIFIED",
    "backup_restore_drill": "NOT_VERIFIED",
    "production_smoke": "NOT_RUN",
    "clinical_approval": "NOT_APPLICABLE",
}

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--json", type=Path, help="Optional new report destination (never overwrites)")
    args = ap.parse_args()
    root = args.root.resolve()
    missing = {group: [p for p in paths if not (root / p).is_file()]
               for group, paths in FILES.items()}
    missing = {k: v for k, v in missing.items() if v}
    absent_docs = [p for p in DOCUMENTS if not (root / p).is_file()]
    readmes = sorted(str(p.relative_to(root)) for p in root.rglob("*")
                     if p.is_file() and p.name.lower() == "readme.md"
                     and not any(x in p.parts for x in (".git", "runtime", "node_modules", ".venv")))
    # A machine cannot certify prose is natural or professionally reviewed.
    prose_flags = []
    for name in readmes:
        data = (root / name).read_text(encoding="utf-8", errors="replace")
        if re.search(r"\b(behavior|authorization|center|analyze)\b", data, re.I):
            prose_flags.append(name + ": review potential US-English spelling")
        if len(data.strip()) < 150:
            prose_flags.append(name + ": brief README requires editorial review")
    result = {
        "repository": "afyaevidence",
        "code_structure": "PASS" if not missing else "FAIL",
        "missing_files": missing,
        "documentation_structure": "PASS" if not absent_docs else "FAIL",
        "missing_documents": absent_docs,
        "readmes_found": readmes,
        "readme_editorial_flags": prose_flags,
        "readme_human_editorial_review": "REQUIRED",
        "verified_local_tests": "OPERATOR_REPORTED_319_AS_OF_20261025_NOT_EXECUTED_BY_THIS_AUDIT",
        "release_gates": RELEASE_GATES,
        "release_decision": "BLOCKED",
    }
    print("PROJECT_STRUCTURE=" + result["code_structure"])
    print("DOCUMENTATION_STRUCTURE=" + result["documentation_structure"])
    print("README_FILES=" + str(len(readmes)))
    for name in readmes: print("README_FOUND=" + name)
    for item in prose_flags: print("README_EDITORIAL_FLAG=" + item)
    print("INDEPENDENT_SECURITY_REVIEW=PENDING")
    print("CONTAINER_SECURITY=BLOCKED_BY_REPORTED_CVES")
    print("PROJECT_RELEASE=BLOCKED")
    if args.json:
        out = args.json.resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("x", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print("AUDIT_REPORT=" + str(out))
    return 0 if not missing and not absent_docs else 1

if __name__ == "__main__":
    sys.exit(main())
