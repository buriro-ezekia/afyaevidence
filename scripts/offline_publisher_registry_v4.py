#!/usr/bin/env python3
"""v4: root-signed, versioned offline publisher trust and revocation registry.

A trusted root is provisioned independently. Offline verification is bounded
by registry expiry and a persistent rollback floor. This cannot detect new
revocations until a recipient installs a newer authenticated registry.
"""
from __future__ import annotations
import argparse
import base64
import binascii
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import offline_evidence_package_v3 as v3
from offline_evidence_package_v2 import canonical, inspect, load_json

REGISTRY_FORMAT = "afya-publisher-trust-registry-4"
REGISTRY_DOMAIN = b"AfyaEvidence/publisher-trust-registry-v4/Ed25519\x00"
HEX = re.compile(r"^[a-f0-9]{64}$")
PUBLISHER = re.compile(r"^[a-z][a-z0-9_-]{2,60}$")
MAX_REGISTRY = 16000
MAX_OFFLINE_HOURS = 72
MAX_VALIDITY_DAYS = 30
MAX_KEYS = 32


def when(value):
    if not isinstance(value, str):
        raise ValueError("invalid_utc")
    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("missing_timezone")
    return value.astimezone(timezone.utc)


def encoded(key):
    return base64.b64encode(v3.raw_public(key)).decode("ascii")


def decode_public(value):
    if not isinstance(value, str):
        raise ValueError("invalid_public_key_encoding")
    raw = base64.b64decode(value, validate=True)
    if len(raw) != 32:
        raise ValueError("invalid_public_key_length")
    return Ed25519PublicKey.from_public_bytes(raw)


def create_registry(args, now=None):
    now = now or datetime.now(timezone.utc)
    if args.output.exists():
        raise ValueError("registry_output_exists")
    if type(args.version) is not int or args.version < 1:
        raise ValueError("invalid_version")
    if not 1 <= args.valid_hours <= MAX_VALIDITY_DAYS * 24:
        raise ValueError("invalid_validity_window")
    root = v3.load_private(args.root_private)
    publisher = v3.load_public(args.publisher_public)
    publisher_id = v3.key_id(publisher)
    if not PUBLISHER.fullmatch(args.publisher):
        raise ValueError("invalid_publisher")
    if args.revoke and not args.previous_registry:
        raise ValueError("revocation_requires_previous_registry")
    entries = []
    if args.previous_registry:
        previous = load_json(v3.safe_file(args.previous_registry))
        payload = validate_registry(previous, root.public_key(), now, freshness=False)
        if args.version != payload["version"] + 1:
            raise ValueError("registry_version_not_sequential")
        entries = [dict(item) for item in payload["publishers"]]
        # A trusted signing root may rotate publishers by adding a new key.
        if any(item["key_id"] == publisher_id and item["publisher"] != args.publisher for item in entries):
            raise ValueError("key_assigned_to_other_publisher")
        if args.revoke:
            if args.revoke not in {item["key_id"] for item in entries}:
                raise ValueError("revoked_key_not_registered")
            for item in entries:
                if item["key_id"] == args.revoke:
                    item["status"] = "revoked"
    if not any(item["key_id"] == publisher_id for item in entries):
        entries.append({"publisher": args.publisher, "key_id": publisher_id,
                        "public_key_b64": encoded(publisher), "status": "active",
                        "valid_from_utc": now.isoformat(),
                        "valid_until_utc": (now + timedelta(days=MAX_VALIDITY_DAYS)).isoformat()})
    if len(entries) > MAX_KEYS:
        raise ValueError("too_many_keys")
    payload = {
        "format": REGISTRY_FORMAT, "version": args.version,
        "root_key_id": v3.key_id(root.public_key()),
        "issued_at_utc": now.isoformat(),
        "expires_at_utc": (now + timedelta(hours=args.valid_hours)).isoformat(),
        "maximum_offline_hours": MAX_OFFLINE_HOURS,
        "publishers": entries,
    }
    sig = root.sign(REGISTRY_DOMAIN + canonical(payload))
    envelope = dict(payload, signature_b64=base64.b64encode(sig).decode("ascii"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as output:
        output.write(canonical(envelope))
    print("TRUST_REGISTRY_CREATE=PASS")
    print("REGISTRY_VERSION=" + str(args.version))
    print("REGISTRY_ROOT_KEY_ID=" + payload["root_key_id"])
    print("REGISTRY_PUBLISHER_KEY_ID=" + publisher_id)
    print("REGISTRY_FILE=" + str(args.output))
    print("TRUST_BOOTSTRAP=NOT_ESTABLISHED_BY_CREATION")
    return 0


def validate_registry(envelope, root, now, *, freshness=True):
    if not isinstance(envelope, dict):
        raise ValueError("invalid_registry")
    mandatory = {"format", "version", "root_key_id", "issued_at_utc",
                 "expires_at_utc", "maximum_offline_hours", "publishers"}
    if set(envelope) != mandatory | {"signature_b64"}:
        raise ValueError("unexpected_registry_fields")
    if envelope["format"] != REGISTRY_FORMAT or type(envelope["version"]) is not int or envelope["version"] < 1:
        raise ValueError("invalid_registry_version")
    if envelope["root_key_id"] != v3.key_id(root):
        raise ValueError("wrong_root")
    if envelope["maximum_offline_hours"] != MAX_OFFLINE_HOURS:
        raise ValueError("invalid_offline_policy")
    signature = base64.b64decode(envelope["signature_b64"], validate=True)
    if len(signature) != 64:
        raise ValueError("invalid_registry_signature_size")
    payload = {key: envelope[key] for key in mandatory}
    root.verify(signature, REGISTRY_DOMAIN + canonical(payload))
    issued, expiry = when(payload["issued_at_utc"]), when(payload["expires_at_utc"])
    if issued > now + timedelta(minutes=5) or expiry <= issued or expiry - issued > timedelta(days=MAX_VALIDITY_DAYS):
        raise ValueError("invalid_registry_timestamps")
    if freshness and (now >= expiry or now - issued > timedelta(hours=MAX_OFFLINE_HOURS)):
        raise ValueError("trust_registry_stale_or_expired")
    entries = payload["publishers"]
    if not isinstance(entries, list) or not entries or len(entries) > MAX_KEYS:
        raise ValueError("invalid_publisher_list")
    ids = set()
    for entry in entries:
        fields = {"publisher", "key_id", "public_key_b64", "status", "valid_from_utc", "valid_until_utc"}
        if not isinstance(entry, dict) or set(entry) != fields:
            raise ValueError("invalid_publisher_entry")
        if not isinstance(entry["publisher"], str) or not PUBLISHER.fullmatch(entry["publisher"]):
            raise ValueError("invalid_publisher_name")
        pub = decode_public(entry["public_key_b64"])
        if entry["key_id"] != v3.key_id(pub) or entry["key_id"] in ids:
            raise ValueError("invalid_or_duplicate_key_id")
        ids.add(entry["key_id"])
        if entry["status"] not in ("active", "revoked"):
            raise ValueError("invalid_key_status")
        if when(entry["valid_from_utc"]) >= when(entry["valid_until_utc"]):
            raise ValueError("invalid_key_validity")
    return payload


@contextmanager
def rollback_guard(state_dir, version, registry_sha):
    if state_dir.is_symlink():
        raise ValueError("unsafe_state_dir")
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if state_dir.stat().st_mode & 0o077:
        raise ValueError("insecure_state_dir")
    lock = state_dir / "registry.lock"
    if lock.is_symlink():
        raise ValueError("unsafe_lock")
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "r+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        state = state_dir / "last_registry.json"
        if state.is_symlink():
            raise ValueError("unsafe_registry_state")
        if state.exists():
            old = load_json(v3.safe_file(state, private=True))
            if set(old) != {"version", "sha256"} or type(old["version"]) is not int:
                raise ValueError("invalid_rollback_state")
            if version < old["version"] or (version == old["version"] and registry_sha != old["sha256"]):
                raise ValueError("registry_rollback_or_equivocation")
        # Pin the authenticated registry floor before assessing a package.
        tmp = state_dir / ("new-registry-" + os.urandom(8).hex())
        try:
            with tmp.open("xb") as out:
                os.chmod(tmp, 0o600)
                out.write(canonical({"version": version, "sha256": registry_sha}))
            os.replace(tmp, state)
        finally:
            tmp.unlink(missing_ok=True)
        yield


def verify_package(args, now=None):
    now = now or datetime.now(timezone.utc)
    if args.registry.stat().st_size > MAX_REGISTRY:
        raise ValueError("registry_too_large")
    root = v3.load_public(args.root_public)
    registry_blob = v3.safe_file(args.registry)
    registry = validate_registry(load_json(registry_blob), root, now)
    expected_hash = sha256(registry_blob).hexdigest()
    if args.signature.stat().st_size > v3.MAX_SIG:
        raise ValueError("signature_too_large")
    envelope = load_json(v3.safe_file(args.signature))
    expected_fields = {"format", "algorithm", "key_id", "package_sha256", "signed_at_utc", "signature_b64"}
    if not isinstance(envelope, dict) or set(envelope) != expected_fields:
        raise ValueError("unexpected_package_signature_fields")
    if envelope["format"] != v3.FORMAT or envelope["algorithm"] != "Ed25519":
        raise ValueError("unsupported_signature")
    key = envelope["key_id"]
    if not isinstance(key, str) or not v3.HEX.fullmatch(key):
        raise ValueError("invalid_signer_key_id")
    evidence = inspect(args.package, None, now)
    if evidence["sha256"] != envelope["package_sha256"]:
        raise ValueError("package_changed")
    signed_at = when(envelope["signed_at_utc"])
    if signed_at > now + timedelta(minutes=5):
        raise ValueError("future_signature")
    entries = [e for e in registry["publishers"] if e["key_id"] == key]
    with rollback_guard(args.state_dir, registry["version"], expected_hash):
        if len(entries) != 1 or entries[0]["status"] != "active":
            raise ValueError("publisher_unknown_or_revoked")
        entry = entries[0]
        if not when(entry["valid_from_utc"]) <= signed_at < when(entry["valid_until_utc"]):
            raise ValueError("signer_outside_validity_window")
        if not when(entry["valid_from_utc"]) <= now < when(entry["valid_until_utc"]):
            raise ValueError("publisher_not_currently_valid")
        public = decode_public(entry["public_key_b64"])
        signature = base64.b64decode(envelope["signature_b64"], validate=True)
        if len(signature) != 64:
            raise ValueError("invalid_package_signature_size")
        payload = {k: envelope[k] for k in expected_fields if k != "signature_b64"}
        public.verify(signature, v3.signed_message(payload))
    print("OFFLINE_V4_TRUST_REGISTRY=PASS")
    print("TRUST_REGISTRY_VERSION=" + str(registry["version"]))
    print("TRUST_REGISTRY_ROOT_KEY_ID=" + registry["root_key_id"])
    print("PUBLISHER_ID=" + entry["publisher"])
    print("PUBLISHER_KEY_STATUS=ACTIVE")
    print("OFFLINE_PACKAGE_SIGNATURE=PASS")
    print("OFFLINE_PACKAGE_INTEGRITY=PASS")
    print("OFFLINE_FRESHNESS=" + evidence["freshness"])
    print("OFFLINE_REVOCATION_STATUS=AS_OF_SIGNED_REGISTRY_ONLY")
    print("ONLINE_REVOCATION_FRESHNESS=NOT_VERIFIED")
    print("OFFLINE_REVIEW_SUBMISSION=DISABLED")
    print("PRODUCTION_RELEASE=BLOCKED")
    return 0 if evidence["freshness"] == "WITHIN_REVIEW_WINDOW" else 3


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-registry")
    create.add_argument("--root-private", type=Path, required=True)
    create.add_argument("--publisher-public", type=Path, required=True)
    create.add_argument("--publisher", required=True)
    create.add_argument("--version", type=int, required=True)
    create.add_argument("--valid-hours", type=int, default=48)
    create.add_argument("--previous-registry", type=Path)
    create.add_argument("--revoke")
    create.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--root-public", type=Path, required=True)
    verify.add_argument("--registry", type=Path, required=True)
    verify.add_argument("--state-dir", type=Path, required=True)
    verify.add_argument("--package", type=Path, required=True)
    verify.add_argument("--signature", type=Path, required=True)
    args = ap.parse_args()
    try:
        return create_registry(args) if args.command == "create-registry" else verify_package(args)
    except (OSError, ValueError, TypeError, KeyError, InvalidSignature, UnicodeError,
            json.JSONDecodeError, binascii.Error):
        print("OFFLINE_V4=BLOCKED_TRUST_OR_POLICY")
        print("PRODUCTION_RELEASE=BLOCKED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
