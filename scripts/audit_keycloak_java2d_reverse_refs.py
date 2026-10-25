#!/usr/bin/env python3
"""Read-only pinned Keycloak JAR reverse-reference audit (not a reachability proof)."""
import argparse
import collections
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zipfile

IMAGE = "quay.io/keycloak/keycloak@sha256:3e1ac632e743660017b1e6bb4c3ffc800fd02c82cdd0db858cd03456a98a8dfc"
IDS = {"sha256:3e1ac632e743660017b1e6bb4c3ffc800fd02c82cdd0db858cd03456a98a8dfc",
       "sha256:b55801be6ce15109868bd056dc18d62d47106bfaad7ffbd1a5d804192ec98257"}
DIRS = {"main": "/opt/keycloak/lib/lib/main", "app": "/opt/keycloak/lib/app",
        "providers": "/opt/keycloak/providers"}
TARGETS = {"JTS_FONT_GLYPH": "org/locationtech/jts/awt/FontGlyphReader",
           "ZXING_MATRIX_IMAGE": "com/google/zxing/client/j2se/MatrixToImageWriter",
           "JAVA_AWT_FONT": "java/awt/Font",
           "JAVA_FONT_PACKAGE": "java/awt/font/",
           "JAVA2D_GRAPHICS": "java/awt/Graphics2D",
           "JAVA_IMAGEIO": "javax/imageio/ImageIO"}

def utf8_constants(data):
    if len(data) < 10 or data[:4] != b"\xca\xfe\xba\xbe":
        raise ValueError("invalid_class_file")
    count = struct.unpack_from(">H", data, 8)[0]
    at, idx, names = 10, 1, []
    while idx < count:
        if at >= len(data):
            raise ValueError("truncated_constant_pool")
        tag = data[at]
        at += 1
        if tag == 1:
            if at + 2 > len(data):
                raise ValueError("truncated_utf_length")
            size = struct.unpack_from(">H", data, at)[0]
            at += 2
            if at + size > len(data):
                raise ValueError("truncated_utf_value")
            names.append(data[at:at + size].decode("utf-8", "replace"))
            at += size
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            at += 4
        elif tag in (5, 6):
            at += 8
            idx += 1
        elif tag in (7, 8, 16, 19, 20):
            at += 2
        elif tag == 15:
            at += 3
        else:
            raise ValueError("unknown_class_tag")
        if at > len(data):
            raise ValueError("truncated_entry")
        idx += 1
    return names

def scan(root):
    matches, errors = [], []
    classes = jars = 0
    sections = {}
    for section in DIRS:
        base = root / section
        paths = sorted(base.rglob("*.jar")) if base.exists() else []
        sections[section] = {"jars": len(paths), "matched_classes": 0}
        if section == "main" and not paths:
            errors.append("main_jars_missing")
        for jar in paths:
            jars += 1
            try:
                with zipfile.ZipFile(jar) as archive:
                    for info in archive.infolist():
                        if not info.filename.endswith(".class"):
                            continue
                        classes += 1
                        if info.file_size > 8000000:
                            errors.append("oversized_class:" + info.filename)
                            continue
                        try:
                            names = utf8_constants(archive.read(info))
                        except ValueError:
                            errors.append("malformed_class:" + info.filename)
                            continue
                        hits = sorted(key for key, value in TARGETS.items()
                                      if any(value in name for name in names))
                        if hits:
                            sections[section]["matched_classes"] += 1
                            matches.append({"section": section,
                                            "jar": str(jar.relative_to(base)),
                                            "class": info.filename,
                                            "references": hits})
            except (OSError, zipfile.BadZipFile):
                errors.append("unreadable_jar:" + str(jar.relative_to(base)))
    return {"jars_scanned": jars, "classes_scanned": classes, "sections": sections,
            "matches": matches, "errors": errors,
            "target_counts": dict(collections.Counter(hit for m in matches for hit in m["references"]))}

def call(*args, timeout=120):
    r = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError("command_failed:" + args[0] + ":" + str(r.returncode))
    return r.stdout.strip()

def pinned():
    info = json.loads(call("docker", "image", "inspect", IMAGE, timeout=40))[0]
    if IMAGE not in info.get("RepoDigests", []) or info.get("Id") not in IDS:
        raise RuntimeError("pinned_image_identity_failed")
    if (info.get("Os"), info.get("Architecture")) != ("linux", "amd64"):
        raise RuntimeError("unexpected_platform")
    return {"id": info["Id"], "reference": IMAGE}

def copy_jars(root):
    cid = call("docker", "create", "--pull", "never",
               "--entrypoint", "/bin/true", IMAGE, timeout=60).splitlines()[-1]
    statuses = {}
    try:
        for section, path in DIRS.items():
            dest = root / section
            dest.mkdir()
            r = subprocess.run(["docker", "cp", cid + ":" + path + "/.", str(dest)],
                               capture_output=True, timeout=180)
            statuses[section] = "PASS" if r.returncode == 0 else "NOT_PRESENT"
        if statuses["main"] != "PASS":
            raise RuntimeError("main_jars_unavailable")
    finally:
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True, timeout=40)
    return statuses

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--offline-directory", type=Path)
    args = parser.parse_args()
    report = args.report.resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    if report.exists():
        print("JAVA2D_REVERSE_AUDIT=BLOCKED_REPORT_EXISTS")
        return 2
    try:
        with tempfile.TemporaryDirectory(prefix="afya-java2d-reverse-") as temp:
            root = Path(temp)
            meta = {}
            if args.offline_directory:
                source = args.offline_directory.resolve()
            else:
                meta["image"] = pinned()
                meta["copy_status"] = copy_jars(root)
                source = root
            data = scan(source)
            if not data["classes_scanned"]:
                raise RuntimeError("no_classes_examined")
            data.update(meta)
            data.update({"scope": "constant_pool_references_only",
                         "application_reachability": "NOT_VERIFIED",
                         "cve_2026_91415": "OPEN", "container_release": "BLOCKED"})
            with report.open("x", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
                fh.write("\n")
            print("JAVA2D_REVERSE_AUDIT=" + ("INCOMPLETE" if data["errors"] else "PASS"))
            print("JARS_SCANNED=" + str(data["jars_scanned"]))
            print("CLASSES_SCANNED=" + str(data["classes_scanned"]))
            print("REFERENCE_CLASSES=" + str(len(data["matches"])))
            for key in TARGETS:
                print(key + "=" + str(data["target_counts"].get(key, 0)))
            for key, values in data["sections"].items():
                print("SECTION_" + key.upper() + "_MATCHES=" + str(values["matched_classes"]))
            print("APPLICATION_REACHABILITY=NOT_VERIFIED")
            print("CVE_2026_91415=OPEN")
            print("CONTAINER_RELEASE=BLOCKED")
            print("JAVA2D_REPORT=" + str(report))
            return 2 if data["errors"] else 0
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print("JAVA2D_REVERSE_AUDIT=BLOCKED_" + type(exc).__name__)
        print("DETAIL=" + str(exc)[:180])
        return 2

if __name__ == "__main__":
    sys.exit(main())
