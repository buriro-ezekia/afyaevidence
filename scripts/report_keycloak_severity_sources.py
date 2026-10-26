#!/usr/bin/env python3
"""Audit Trivy severity attribution for a pinned Keycloak candidate report.

Read-only; distinguishes scanner's cross-vendor severity warning from
unresolved critical/high findings. Never suppresses, re-rates or deletes CVEs.
"""
import argparse
import collections
import json
from pathlib import Path
import sys

LEVELS = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")
TARGETS = ("CVE-2026-91403", "CVE-2026-91415", "CVE-2026-114406")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=Path("runtime/security/keycloak-candidate/candidate-trivy.json"))
    args=parser.parse_args()
    try:
        report=json.loads(args.report.read_text(encoding="utf-8"))
        results=report.get("Results")
        if not isinstance(results,list) or not results or not any(
            isinstance(r,dict) and r.get("Packages") for r in results
        ):
            raise ValueError("incomplete_trivy_inventory")
        count=collections.Counter()
        sources=collections.Counter()
        advisories={}
        for result in results:
            if not isinstance(result,dict):
                raise ValueError("invalid_result")
            for item in result.get("Vulnerabilities") or []:
                severity=item.get("Severity","UNKNOWN")
                source=item.get("SeveritySource") or "UNSPECIFIED"
                count[severity]+=1
                sources[source]+=1
                if item.get("VulnerabilityID") in TARGETS:
                    advisories.setdefault(item["VulnerabilityID"],[]).append(item)
        print("TRIVY_SEVERITY_REPORT=PASS")
        for level in LEVELS:
            print(f"REPORTED_{level}={count[level]}")
        for source in sorted(sources):
            print(f"SEVERITY_SOURCE_{source.upper().replace('-','_')}={sources[source]}")
        for cve in TARGETS:
            entries=advisories.get(cve,[])
            if not entries:
                print(f"{cve}=NOT_REPORTED")
                continue
            for item in entries:
                print(f"{cve}=REPORTED")
                print(f"  PACKAGE={item.get('PkgName','UNKNOWN')}")
                print(f"  SEVERITY={item.get('Severity','UNKNOWN')}")
                print(f"  SEVERITY_SOURCE={item.get('SeveritySource','UNSPECIFIED')}")
                print(f"  VENDOR_RED_HAT_SCORE={item.get('VendorSeverity',{}).get('redhat','NOT_AVAILABLE')}")
                print(f"  FIXED_VERSION={item.get('FixedVersion') or 'NOT_LISTED'}")
        blocked = count["CRITICAL"]>0 or count["HIGH"]>0
        print("CONTAINER_SECURITY=" + ("BLOCKED_BY_CRITICAL_HIGH" if blocked else "REQUIRES_REVIEW"))
        print("NOTE=Severity attribution is informational; CVE findings remain unchanged.")
        return 0
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError):
        print("TRIVY_SEVERITY_REPORT=FAIL")
        return 2

if __name__=="__main__":
    sys.exit(main())
