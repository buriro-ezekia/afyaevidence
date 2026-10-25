#!/usr/bin/env python3
"""Offline Java 2D reachability triage for a pinned Keycloak image.

Reads installed JAR class constant pools as an INDICATOR of Java2D references.
Never executes application code, launches Keycloak, invokes remote endpoints
or asserts that a vulnerability is exploitable or not applicable.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

IMAGE = "quay.io/keycloak/keycloak@sha256:3e1ac632e743660017b1e6bb4c3ffc800fd02c82cdd0db858cd03456a98a8dfc"
MANIFEST = "sha256:3e1ac632e743660017b1e6bb4c3ffc800fd02c82cdd0db858cd03456a98a8dfc"
CONFIG = "sha256:b55801be6ce15109868bd056dc18d62d47106bfaad7ffbd1a5d804192ec98257"

# Constant-pool indicators only: the exact vulnerable Java methods and their
# reachability have not been published in sufficiently precise vendor detail.
MARKERS = {
    "JAVA_AWT": b"java/awt/",
    "JAVA_2D": b"sun/java2d/",
    "JAVA_FONT": b"java/awt/font/",
    "JAVA_IMAGEIO": b"javax/imageio/",
    "JAVA_FONT_ENGINE": b"sun/font/",
}
PATHS = (
    ("/opt/keycloak/lib/lib/main", "main"),
    ("/opt/keycloak/lib/app", "app"),
    ("/opt/keycloak/providers", "providers"),
)

def command(args: list[str], timeout: int = 120) -> str:
    result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"command_failed:{args[0]}:{args[1]}:exit_{result.returncode}")
    return result.stdout.strip()

def require_image() -> dict:
    details = json.loads(command(["docker", "image", "inspect", IMAGE], 30))[0]
    if IMAGE not in details.get("RepoDigests", []):
        raise RuntimeError("pinned_repo_digest_not_verified")
    identity = details.get("Id")
    if identity not in (MANIFEST, CONFIG):
        raise RuntimeError("unrecognised_docker_image_id")
    platform = (details.get("Os"), details.get("Architecture"))
    if platform != ("linux", "amd64"):
        raise RuntimeError("unexpected_image_platform")
    return {"repo_digest": IMAGE, "docker_id": identity, "platform": "linux/amd64"}

def scan_jar(path: Path, max_class_bytes: int = 8_000_000):
    matched = []
    classes = 0
    skipped = 0
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if not info.filename.endswith(".class"):
                continue
            classes += 1
            if info.file_size > max_class_bytes:
                skipped += 1
                continue
            payload = z.read(info, pwd=None)
            hints = [k for k, marker in MARKERS.items() if marker in payload]
            if hints:
                matched.append({"class": info.filename, "markers": hints})
    return classes, skipped, matched

def inspect_tree(folder: Path):
    result = {"jars": 0, "classes": 0, "classes_skipped": 0, "matched_classes": 0,
              "jar_matches": [], "failed_jars": []}
    for jar in sorted(folder.rglob("*.jar")):
        result["jars"] += 1
        try:
            classes, skipped, matches = scan_jar(jar)
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, EOFError) as exc:
            result["failed_jars"].append({"jar": str(jar.relative_to(folder)), "error": type(exc).__name__})
            continue
        result["classes"] += classes
        result["classes_skipped"] += skipped
        result["matched_classes"] += len(matches)
        if matches:
            result["jar_matches"].append({
                "jar": str(jar.relative_to(folder)),
                "matched_classes": len(matches),
                "sample": matches[:12],
                "markers": dict(Counter(hint for m in matches for hint in m["markers"]))
            })
    return result

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="A new JSON output path; never overwritten")
    parser.add_argument("--offline-directory", type=Path,
                        help="Analyse an already exported, trusted Keycloak filesystem; avoids Docker")
    args = parser.parse_args()
    report = args.report.resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    if report.exists():
        print("JAVA2D_AUDIT=BLOCKED_REPORT_EXISTS")
        return 2
    try:
        with tempfile.TemporaryDirectory(prefix="afya-keycloak2d-") as tmp:
            root = Path(tmp)
            evidence = {"method": "offline_tree" if args.offline_directory else "pinned_docker_create_copy",
                        "scope": "static_constant_pool_markers_only",
                        "vendor_advisory": "CVE-2026-91415",
                        "runtime_route_reachability": "NOT_VERIFIED",
                        "java_2d_vulnerability_status": "REPORTED_AFFECTED",
                        "production_acceptance": "BLOCKED"}
            if args.offline_directory:
                base = args.offline_directory.resolve()
            else:
                evidence["image"] = require_image()
                # Create but NEVER start a container. No realm mounts or network.
                cid = command(["docker", "create", "--pull", "never",
                               "--entrypoint", "/bin/true", IMAGE], 60).splitlines()[-1]
                try:
                    base = root / "image"
                    base.mkdir()
                    for source, label in PATHS:
                        target = base / label
                        result = subprocess.run(
                            ["docker", "cp", f"{cid}:{source}/.", str(target)],
                            check=False, capture_output=True, text=True, timeout=180)
                        if result.returncode:
                            evidence[f"copy_{label}"] = "UNAVAILABLE"
                        else:
                            evidence[f"copy_{label}"] = "PASS"
                    if evidence.get("copy_main") != "PASS":
                        raise RuntimeError("keycloak_main_jar_directory_unavailable")
                finally:
                    subprocess.run(["docker", "rm", "-f", cid], capture_output=True, timeout=30, check=False)
            evidence["sections"] = {}
            for _, label in PATHS:
                folder = base / label
                evidence["sections"][label] = inspect_tree(folder) if folder.exists() else {"status": "NOT_PRESENT"}
            sections = evidence["sections"]
            evidence["jar_count"] = sum(x.get("jars", 0) for x in sections.values())
            evidence["class_count"] = sum(x.get("classes", 0) for x in sections.values())
            evidence["matched_classes"] = sum(x.get("matched_classes", 0) for x in sections.values())
            evidence["incomplete"] = any(x.get("classes_skipped") or x.get("failed_jars") for x in sections.values())
            if not evidence["jar_count"] or not evidence["class_count"]:
                raise RuntimeError("no_java_classes_examined")
            with report.open("x", encoding="utf-8") as f:
                json.dump(evidence, f, indent=2)
                f.write("\n")
            print("JAVA2D_STATIC_INVENTORY=PASS" if not evidence["incomplete"] else "JAVA2D_STATIC_INVENTORY=INCOMPLETE")
            print("JARS_SCANNED=" + str(evidence["jar_count"]))
            print("CLASSES_SCANNED=" + str(evidence["class_count"]))
            print("CLASSES_WITH_2D_REFERENCES=" + str(evidence["matched_classes"]))
            print("APPLICATION_REACHABILITY=NOT_VERIFIED")
            print("CVE_2026_91415=OPEN")
            print("CONTAINER_RELEASE=BLOCKED")
            print("JAVA2D_REPORT=" + str(report))
            return 0 if not evidence["incomplete"] else 2
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print("JAVA2D_AUDIT=BLOCKED_" + type(exc).__name__)
        print("DETAIL=" + str(exc)[:160])
        return 2

if __name__ == "__main__":
    sys.exit(main())
