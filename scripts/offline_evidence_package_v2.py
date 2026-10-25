#!/usr/bin/env python3
"""Create or verify portable, read-only synthetic evidence packages.

SHA-256 checks detect changes against the supplied manifest; they do NOT
authenticate the author. An out-of-band expected ZIP hash is needed to detect
an attacker who rewrites both content and manifest. No raw health records,
identity claims, review actions or offline synchronisation are packaged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import sys
import zipfile

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from export_offline_briefcase import MAX_RECEIPT, render, validate

NAMES = ("manifest.json", "briefcase.html", "evidence.json")
MAX_PACKAGE = 2_000_000
MAX_ENTRY = 900_000
HEX = re.compile(r"^[0-9a-f]{64}$")


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def pairs_unique(pairs):
    doc = {}
    for key, value in pairs:
        if key in doc:
            raise ValueError("duplicate_json_key")
        doc[key] = value
    return doc


def load_json(blob):
    return json.loads(blob, object_pairs_hook=pairs_unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(
                          ValueError("nonfinite_json")))


def utc(text):
    if not isinstance(text, str):
        raise ValueError("invalid_date")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone_required")
    return parsed.astimezone(timezone.utc)


def digest(blob):
    return sha256(blob).hexdigest()


def extract(document):
    brief, evidence = validate(document)
    metrics = {m["metric_ref"]: m for m in evidence["metrics"]}
    cited_metrics = []
    for statement in brief["numerical_statements"]:
        m = metrics[statement["metric_ref"]]
        # Do not carry source records, source tables, patient details, identity,
        # memory, reviewer notes or optional arbitrary metadata into the ZIP.
        cited_metrics.append({
            "metric_ref": m["metric_ref"], "period": m["period"],
            "cohort": m["cohort"], "view": m["view"], "name": m["name"],
            "value": m["value"], "unit": m["unit"],
            "evidence_ids": statement["evidence_ids"],
        })
    return {
        "format": "afya-offline-evidence-2",
        "data_mode": "fixture",
        "model_mode": "scripted",
        "review_status": "awaiting_human_review",
        "snapshot_id": evidence["snapshot_id"],
        "summary": brief["summary"],
        "explanation": brief.get("explanation"),
        "numerical_statements": [row["text"] for row in brief["numerical_statements"]],
        "cited_evidence_ids": brief["evidence_ids"],
        "metrics": cited_metrics,
        "limitations": brief["limitations"],
        "next_checks": brief["next_checks"],
        "approval": None,
    }


def build(receipt, now, hours):
    if hours < 1 or hours > 168:
        raise ValueError("invalid_validity_window")
    if len(receipt) > MAX_RECEIPT:
        raise ValueError("oversized_receipt")
    document = load_json(receipt)
    reduced = extract(document)
    html = render(document, digest(receipt))
    created = now.astimezone(timezone.utc)
    until = created + timedelta(hours=hours)
    # A static file cannot know today's date without a clock or scripts.
    # It therefore always warns that content may be stale when reopened.
    banner = ('<section aria-label="Freshness"><h2>Offline freshness warning</h2>'
              '<p><strong>Previously prepared evidence. This copy may now be stale.</strong> '
              'It is not refreshed while offline. Verify its timestamp and hash '
              'before relying on it.</p>'
              '<p>Prepared UTC: <code>' + escape(created.isoformat()) +
              '</code>. Review-by UTC: <code>' + escape(until.isoformat()) +
              '</code>.</p></section>')
    if "</body>" not in html:
        raise ValueError("html_template_invalid")
    html = html.replace("</body>", banner + "</body>")
    files = {"briefcase.html": html.encode("utf-8"), "evidence.json": canonical(reduced)}
    manifest = {
        "format": "afya-offline-package-2",
        "created_at_utc": created.isoformat(),
        "review_by_utc": until.isoformat(),
        "source_receipt_sha256": digest(receipt),
        "snapshot_id": reduced["snapshot_id"],
        "mode": "synthetic_scripted_read_only",
        "security": {"signature": "NOT_SIGNED", "authenticated_offline_review": False,
                     "offline_submission": False, "source_refresh": False},
        "files": {name: {"sha256": digest(data), "bytes": len(data)}
                  for name, data in sorted(files.items())},
    }
    files["manifest.json"] = canonical(manifest)
    if sum(len(v) for v in files.values()) > MAX_PACKAGE:
        raise ValueError("package_too_large")
    return files


def create(args):
    if args.output.exists():
        raise FileExistsError("output_exists")
    raw = args.receipt.read_bytes()
    files = build(raw, datetime.now(timezone.utc), args.valid_hours)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation avoids overwriting an immutable report.
    with args.output.open("xb") as stream:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name in NAMES:
                bundle.writestr(name, files[name])
    print("OFFLINE_PACKAGE=PASS")
    print("PACKAGE_SHA256=" + digest(args.output.read_bytes()))
    print("PACKAGE_MODE=synthetic_scripted_read_only")
    print("OFFLINE_REVIEW_SUBMISSION=DISABLED")
    print("OFFLINE_AUTHENTICATION=NOT_SUPPORTED")
    print("OFFLINE_OUTPUT=" + str(args.output))
    return 0


def inspect(path, expected, now):
    if not path.is_file() or path.stat().st_size > MAX_PACKAGE:
        raise ValueError("invalid_package_size")
    package_bytes = path.read_bytes()
    package_sha = digest(package_bytes)
    if expected is not None:
        if HEX.fullmatch(expected) is None or expected != package_sha:
            raise ValueError("expected_hash_mismatch")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) != 3 or {i.filename for i in members} != set(NAMES):
            raise ValueError("unexpected_zip_members")
        if any(i.is_dir() or i.flag_bits & 1 or
               i.file_size > MAX_ENTRY or i.compress_size > MAX_PACKAGE or
               i.filename.startswith("/") or "/" in i.filename or "\\" in i.filename
               for i in members):
            raise ValueError("unsafe_zip_member")
        if sum(i.file_size for i in members) > MAX_PACKAGE:
            raise ValueError("zip_expansion_limit")
        data = {name: archive.read(name) for name in NAMES}
    manifest = load_json(data["manifest.json"])
    evidence = load_json(data["evidence.json"])
    if manifest.get("format") != "afya-offline-package-2":
        raise ValueError("unsupported_format")
    if manifest.get("mode") != "synthetic_scripted_read_only":
        raise ValueError("unsupported_mode")
    if manifest.get("security") != {
        "signature": "NOT_SIGNED", "authenticated_offline_review": False,
        "offline_submission": False, "source_refresh": False
    }:
        raise ValueError("invalid_security_contract")
    if evidence.get("format") != "afya-offline-evidence-2" or evidence.get("approval") is not None:
        raise ValueError("invalid_evidence_status")
    if evidence.get("data_mode") != "fixture" or evidence.get("model_mode") != "scripted":
        raise ValueError("non_synthetic_evidence")
    if evidence.get("review_status") != "awaiting_human_review":
        raise ValueError("invalid_review_status")
    if manifest.get("snapshot_id") != evidence.get("snapshot_id"):
        raise ValueError("snapshot_mismatch")
    if not isinstance(manifest.get("source_receipt_sha256"), str) or not HEX.fullmatch(manifest["source_receipt_sha256"]):
        raise ValueError("invalid_source_hash")
    expected_members = manifest.get("files")
    if not isinstance(expected_members, dict) or set(expected_members) != {"briefcase.html", "evidence.json"}:
        raise ValueError("invalid_file_manifest")
    for name in ("briefcase.html", "evidence.json"):
        info = expected_members[name]
        if not isinstance(info, dict) or info != {"sha256": digest(data[name]), "bytes": len(data[name])}:
            raise ValueError("file_integrity_mismatch")
    html = data["briefcase.html"].decode("utf-8")
    if ("Content-Security-Policy" not in html or
        "READ-ONLY" not in html or "AWAITING HUMAN REVIEW" not in html or
        "This copy may now be stale" not in html or
        "<script" in html.lower() or "<form" in html.lower()):
        raise ValueError("unsafe_view")
    created, expiry = utc(manifest.get("created_at_utc")), utc(manifest.get("review_by_utc"))
    if expiry <= created or expiry-created > timedelta(days=7) or created > now + timedelta(minutes=5):
        raise ValueError("invalid_freshness_window")
    return {"sha256": package_sha,
            "freshness": "STALE" if now >= expiry else "WITHIN_REVIEW_WINDOW",
            "expires": expiry.isoformat(), "signature": "NOT_SIGNED"}


def verify(args):
    status = inspect(args.package, args.expected_sha256, datetime.now(timezone.utc))
    print("OFFLINE_PACKAGE_INTEGRITY=PASS")
    print("OFFLINE_PACKAGE_SHA256=" + status["sha256"])
    print("OFFLINE_FRESHNESS=" + status["freshness"])
    print("REVIEW_BY_UTC=" + status["expires"])
    print("AUTHOR_AUTHENTICITY=NOT_VERIFIED_UNSIGNED_PACKAGE")
    print("OFFLINE_REVIEW_SUBMISSION=DISABLED")
    print("CONTAINER_RELEASE=BLOCKED")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("create")
    c.add_argument("--receipt", required=True, type=Path)
    c.add_argument("--output", required=True, type=Path)
    c.add_argument("--valid-hours", type=int, default=48)
    v = sub.add_parser("verify")
    v.add_argument("--package", required=True, type=Path)
    v.add_argument("--expected-sha256", help="A trusted SHA-256 received independently")
    args = p.parse_args()
    try:
        return create(args) if args.command == "create" else verify(args)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, zipfile.BadZipFile, RuntimeError):
        print("OFFLINE_PACKAGE=BLOCKED_INTEGRITY_OR_POLICY")
        return 2


if __name__ == "__main__":
    sys.exit(main())
