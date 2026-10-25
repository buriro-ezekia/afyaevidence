#!/usr/bin/env python3
"""Offline Evidence Package v3: detached Ed25519 signatures and explicit trust.

Signature verification authenticates a package only relative to a trusted
public key deliberately installed by its recipient. It does not provide
offline user authentication, revocation updates or review submission.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from offline_evidence_package_v2 import inspect, canonical, load_json

FORMAT = "afya-offline-signature-3"
DOMAIN = b"AfyaEvidence/offline-package-v3/Ed25519\x00"
HEX = re.compile(r"^[a-f0-9]{64}$")
MAX_SIG = 4096


def raw_public(key):
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def key_id(key):
    return sha256(raw_public(key)).hexdigest()


def signed_message(payload):
    return DOMAIN + canonical(payload)


def safe_file(path, *, private=False):
    if path.is_symlink() or not path.is_file():
        raise ValueError("unsafe_key_path")
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode):
        raise ValueError("not_regular_file")
    if private and mode & 0o077:
        raise ValueError("private_key_permissions")
    return path.read_bytes()


def keygen(args):
    if args.private_key.exists() or args.public_key.exists():
        raise ValueError("key_output_exists")
    if args.private_key.parent.resolve() != args.public_key.parent.resolve():
        raise ValueError("key_outputs_must_share_private_directory")
    args.private_key.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.private_key.parent.stat().st_mode & 0o077:
        raise ValueError("unsafe_key_directory")
    private = Ed25519PrivateKey.generate()
    secret = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                   serialization.NoEncryption())
    public = private.public_key()
    pub_pem = public.public_bytes(serialization.Encoding.PEM,
                                  serialization.PublicFormat.SubjectPublicKeyInfo)
    fd = os.open(args.private_key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(secret)
        with args.public_key.open("xb") as output:
            output.write(pub_pem)
    except Exception:
        # Don't leave an orphaned new private key if public-key writing fails.
        args.private_key.unlink(missing_ok=True)
        raise
    print("OFFLINE_KEYGEN=PASS")
    print("PUBLIC_KEY_ID=" + key_id(public))
    print("PRIVATE_KEY_STORAGE=OWNER_ONLY_UNENCRYPTED_DEVELOPMENT_KEY")
    print("TRUST_ON_RECIPIENT=NOT_CONFIGURED")
    return 0


def load_private(path):
    key = serialization.load_pem_private_key(safe_file(path, private=True), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("not_ed25519_private")
    return key


def load_public(path):
    key = serialization.load_pem_public_key(safe_file(path))
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("not_ed25519_public")
    return key


def sign(args, now=None):
    if args.signature.exists():
        raise ValueError("signature_exists")
    now = now or datetime.now(timezone.utc)
    evidence = inspect(args.package, None, now)
    if evidence["freshness"] != "WITHIN_REVIEW_WINDOW":
        raise ValueError("stale_package_not_signable")
    private = load_private(args.private_key)
    pub_id = key_id(private.public_key())
    payload = {
        "format": FORMAT, "algorithm": "Ed25519",
        "key_id": pub_id, "package_sha256": evidence["sha256"],
        "signed_at_utc": now.astimezone(timezone.utc).isoformat(),
    }
    signature = private.sign(signed_message(payload))
    envelope = dict(payload, signature_b64=base64.b64encode(signature).decode("ascii"))
    args.signature.parent.mkdir(parents=True, exist_ok=True)
    with args.signature.open("xb") as output:
        output.write(canonical(envelope))
    print("OFFLINE_PACKAGE_SIGNING=PASS")
    print("SIGNED_PACKAGE_SHA256=" + evidence["sha256"])
    print("SIGNING_KEY_ID=" + pub_id)
    print("SIGNATURE_FILE=" + str(args.signature))
    print("RECIPIENT_TRUST=NOT_ESTABLISHED_BY_SIGNING")
    return 0


def verify(args, now=None):
    now = now or datetime.now(timezone.utc)
    # Validate the underlying v2 package *before* relying on its presentation.
    evidence = inspect(args.package, None, now)
    if not args.signature.is_file() or args.signature.stat().st_size > MAX_SIG:
        raise ValueError("signature_file_invalid")
    envelope = load_json(args.signature.read_bytes())
    fields = {"format", "algorithm", "key_id", "package_sha256",
              "signed_at_utc", "signature_b64"}
    if not isinstance(envelope, dict) or set(envelope) != fields:
        raise ValueError("signature_fields_invalid")
    if envelope["format"] != FORMAT or envelope["algorithm"] != "Ed25519":
        raise ValueError("unsupported_signature")
    kid, expected_sha = envelope["key_id"], envelope["package_sha256"]
    if (not isinstance(kid, str) or not HEX.fullmatch(kid) or
        not isinstance(expected_sha, str) or not HEX.fullmatch(expected_sha) or
        expected_sha != evidence["sha256"]):
        raise ValueError("package_hash_or_key_invalid")
    issued = datetime.fromisoformat(envelope["signed_at_utc"].replace("Z", "+00:00"))
    if issued.tzinfo is None or issued > now + timedelta(minutes=5):
        raise ValueError("invalid_signing_time")
    # Explicit pinned trust store, never a public key from the untrusted ZIP
    # or signature envelope. Directory entries are operator-provisioned.
    if not args.trust_dir.is_dir() or args.trust_dir.is_symlink():
        raise ValueError("missing_trust_store")
    public_path = args.trust_dir / (kid + ".pem")
    public = load_public(public_path)
    if key_id(public) != kid:
        raise ValueError("trusted_key_identity_mismatch")
    sig_text = envelope["signature_b64"]
    if not isinstance(sig_text, str) or len(sig_text) > 128:
        raise ValueError("signature_encoding_invalid")
    raw = base64.b64decode(sig_text, validate=True)
    if len(raw) != 64:
        raise ValueError("signature_length_invalid")
    payload = {k: envelope[k] for k in fields if k != "signature_b64"}
    public.verify(raw, signed_message(payload))
    print("OFFLINE_PACKAGE_SIGNATURE=PASS")
    print("OFFLINE_PACKAGE_INTEGRITY=PASS")
    print("TRUSTED_PUBLISHER_KEY_ID=" + kid)
    print("OFFLINE_FRESHNESS=" + evidence["freshness"])
    print("TRUST_BASIS=EXPLICIT_LOCALLY_INSTALLED_KEY")
    print("OFFLINE_REVOCATION_STATUS=NOT_CHECKED")
    print("OFFLINE_REVIEW_SUBMISSION=DISABLED")
    print("PRODUCTION_RELEASE=BLOCKED")
    return 0 if evidence["freshness"] == "WITHIN_REVIEW_WINDOW" else 3


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    k = sub.add_parser("keygen")
    k.add_argument("--private-key", type=Path, required=True)
    k.add_argument("--public-key", type=Path, required=True)
    s = sub.add_parser("sign")
    s.add_argument("--package", type=Path, required=True)
    s.add_argument("--private-key", type=Path, required=True)
    s.add_argument("--signature", type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("--package", type=Path, required=True)
    v.add_argument("--signature", type=Path, required=True)
    v.add_argument("--trust-dir", type=Path, required=True)
    args = ap.parse_args()
    try:
        return {"keygen": keygen, "sign": sign, "verify": verify}[args.command](args)
    except (OSError, ValueError, TypeError, KeyError, InvalidSignature, UnicodeError,
            json.JSONDecodeError):
        print("OFFLINE_PACKAGE_V3=BLOCKED_SIGNATURE_OR_TRUST")
        print("AUTHENTICITY=NOT_VERIFIED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
