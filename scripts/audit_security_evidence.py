#!/usr/bin/env python3
"""Read-only dependency and pinned Keycloak Trivy evidence audit.

The report never updates dependencies, images or keys and never claims
that a passing pip check equals vulnerability clearance.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import importlib.metadata as metadata
import json
from pathlib import Path
import re
import subprocess
import sys

TARGET = {"CVE-2026-91403", "CVE-2026-91415"}
EXPECTED_MANIFEST = "sha256:3e1ac632e743660017b1e6bb4c3ffc800fd02c82cdd0db858cd03456a98a8dfc"
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")
MAX_REPORT = 25_000_000


def analyse(report):
    if not isinstance(report, dict) or not isinstance(report.get("Results"), list):
        raise ValueError("invalid_trivy_report")
    results = report["Results"]
    if not results or not any(isinstance(item, dict) and isinstance(item.get("Packages"), list)
                              and item["Packages"] for item in results):
        raise ValueError("missing_package_inventory")
    findings = Counter()
    tracked = set()
    packages = 0
    for section in results:
        if not isinstance(section, dict):
            raise ValueError("invalid_trivy_section")
        packages += len(section.get("Packages") or [])
        for finding in section.get("Vulnerabilities") or []:
            if not isinstance(finding, dict):
                raise ValueError("invalid_vulnerability")
            severity = finding.get("Severity", "UNKNOWN")
            if severity not in SEVERITIES:
                severity = "UNKNOWN"
            findings[severity] += 1
            if finding.get("VulnerabilityID") in TARGET:
                tracked.add(finding["VulnerabilityID"])
    return packages, findings, tracked


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trivy-report", required=True, type=Path,
                    help="Existing JSON scan report for the independently pinned candidate")
    ap.add_argument("--out", required=True, type=Path, help="New JSON evidence file")
    ap.add_argument("--image-manifest", default=EXPECTED_MANIFEST,
                    help="Previously checked candidate manifest digest")
    args = ap.parse_args()
    if args.out.exists():
        print("SECURITY_AUDIT=BLOCKED_OUTPUT_EXISTS")
        return 2
    try:
        if args.image_manifest != EXPECTED_MANIFEST:
            raise ValueError("unexpected_candidate_image")
        if not args.trivy_report.is_file() or args.trivy_report.stat().st_size > MAX_REPORT:
            raise ValueError("missing_or_large_scan")
        blob = args.trivy_report.read_bytes()
        packages, findings, tracked = analyse(json.loads(blob))
        required = {"PyJWT", "cryptography", "setuptools"}
        installed = {}
        for name in sorted(required):
            installed[name] = metadata.version(name)
        pip = subprocess.run([sys.executable, "-m", "pip", "check"],
                             capture_output=True, text=True, timeout=40)
        data = {
            "schema": "afya-security-evidence-1",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "candidate_manifest": EXPECTED_MANIFEST,
            "candidate_runtime_identity": "NOT_RECHECKED_BY_THIS_REPORT",
            "trivy_input": str(args.trivy_report),
            "trivy_sha256": sha256(blob).hexdigest(),
            "trivy_database_freshness": "NOT_VERIFIED",
            "package_entries": packages,
            "vulnerabilities": {level: findings[level] for level in SEVERITIES},
            "tracked_advisories_reported": sorted(tracked),
            "tracked_advisories_absent_not_proof_of_fix": sorted(TARGET - tracked),
            "python_dependencies": installed,
            "pip_check": "PASS" if pip.returncode == 0 else "FAIL",
            "pip_check_output": (pip.stdout + pip.stderr)[-3000:],
            "python_vulnerability_scan": "NOT_RUN",
            "dependency_lock_review": "PENDING",
            "independent_security_review": "PENDING",
            "container_release": "BLOCKED",
            "production_release": "BLOCKED",
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8") as output:
            json.dump(data, output, indent=2, ensure_ascii=False)
            output.write("\n")
        print("SECURITY_AUDIT_EVIDENCE=PASS")
        print("CANDIDATE_MANIFEST=" + EXPECTED_MANIFEST)
        print("TRIVY_PACKAGE_ENTRIES=" + str(packages))
        for level in SEVERITIES:
            print("TRIVY_" + level + "=" + str(findings[level]))
        for cve in sorted(TARGET):
            print(cve + "=" + ("REPORTED" if cve in tracked else "NOT_REPORTED_NOT_CLEARED"))
        print("PYTHON_PIP_CHECK=" + data["pip_check"])
        print("DEPENDENCY_VULNERABILITY_AUDIT=NOT_RUN")
        print("CONTAINER_RELEASE=BLOCKED")
        print("PRODUCTION_RELEASE=BLOCKED")
        print("SECURITY_AUDIT_OUTPUT=" + str(args.out))
        return 0 if pip.returncode == 0 else 2
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError,
            metadata.PackageNotFoundError, subprocess.TimeoutExpired):
        print("SECURITY_AUDIT_EVIDENCE=BLOCKED_INCOMPLETE_INPUT")
        print("CONTAINER_RELEASE=BLOCKED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
