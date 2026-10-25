# Offline Evidence Packages v3 — signed and trusted distribution

This slice builds on the [v2 offline package](OFFLINE_EVIDENCE_PACKAGES_V2.md).
It adds an **Ed25519 detached signature** for the exact v2 ZIP and requires a
**separately installed, explicitly trusted publisher public key** during
verification. It remains an offline, synthetic, read-only demonstration.

The signature establishes that the package was signed using the private key
corresponding to the *locally trusted public key*. It does **not** establish
the real-world identity or authority of a publisher merely from a key
fingerprint; that trust must be confirmed outside the package.

## Files and boundaries

- The existing v2 ZIP is left byte-for-byte unchanged. Its own manifest,
  content limits, synthetic-only checks, stale warning and human-review
  boundary remain mandatory.
- A separate `*.sig.json` stores the signature, timestamp, ZIP SHA-256,
  Ed25519 algorithm and a SHA-256 identifier for the public key.
- The verifier accepts **only a public key already installed** in a trusted
  local directory as `<key-id>.pem`. A public key supplied alongside an
  untrusted package must not be automatically trusted.
- The detached signature is domain-separated for AfyaEvidence package v3,
  and protects the canonical signed metadata, including the exact ZIP
  SHA-256.
- The recipient must maintain a trusted clock: expired packages are reported
  as stale, not approved for current use. A stale but cryptographically valid
  package produces exit code 3.

There is **no** cached OAuth token, user login, offline decision form,
approval authority, synchronisation queue or background upload.

## Generate a development-only signing key

In Terminal 2, with Python 3.12 and the existing isolated Python environment:

```bash
cd "$HOME/afyaevidence-keycloak-live"
source "$HOME/.venvs/afyaevidence-identity/bin/activate"
umask 077

mkdir -p "$HOME/.local/state/afyaevidence-signing"
chmod 700 "$HOME/.local/state/afyaevidence-signing"

python scripts/offline_evidence_package_v3.py keygen \\
  --private-key "$HOME/.local/state/afyaevidence-signing/dev-private.pem" \\
  --public-key "$HOME/.local/state/afyaevidence-signing/dev-public.pem"
```

This creates an **unencrypted, owner-only development private key** outside
Git. It is intended only for an isolated synthetic demonstration. Do not
use it for real public-health data, deploy it, copy it into a container,
post it in chat or include it in the ZIP. A production key requires a
reviewed organisational key-management process, suitable key protection,
rotation and revocation controls.

The command prints a public-key ID. Establish the publisher identity and
fingerprint independently before trusting any public key.

## Sign the existing verified ZIP

Use the v2 ZIP that already passed `OFFLINE_PACKAGE_INTEGRITY=PASS`:

```bash
python scripts/offline_evidence_package_v3.py sign \\
  --package runtime/offline-evidence-package-v2.zip \\
  --private-key "$HOME/.local/state/afyaevidence-signing/dev-private.pem" \\
  --signature runtime/offline-evidence-package-v2.sig.json
```

The signer rechecks the v2 ZIP and refuses to sign it after the review-by
time. Signatures and keys are never overwritten. Choose new paths for new
runs; do not delete original evidence files.

## Establish explicit local trust and verify offline

For this **single-machine development test only**, copy the trusted public
key into a separate recipient-side trust directory, naming the file after
the key ID printed by `keygen`. On a second computer, distribute the
verified public key through an independently trusted channel, not merely
alongside an untrusted ZIP.

```bash
mkdir -p "$HOME/.config/afyaevidence/trusted-publishers"
chmod 700 "$HOME/.config/afyaevidence/trusted-publishers"

KEY_ID="$(python - <<'PY'
import hashlib
from pathlib import Path
from cryptography.hazmat.primitives import serialization
p = Path.home()/'.local/state/afyaevidence-signing/dev-public.pem'
key = serialization.load_pem_public_key(p.read_bytes())
raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
print(hashlib.sha256(raw).hexdigest())
PY
)"

cp -n "$HOME/.local/state/afyaevidence-signing/dev-public.pem" \\
  "$HOME/.config/afyaevidence/trusted-publishers/$KEY_ID.pem"

python scripts/offline_evidence_package_v3.py verify \\
  --package runtime/offline-evidence-package-v2.zip \\
  --signature runtime/offline-evidence-package-v2.sig.json \\
  --trust-dir "$HOME/.config/afyaevidence/trusted-publishers"
```

Successful results include `OFFLINE_PACKAGE_SIGNATURE=PASS`,
`OFFLINE_PACKAGE_INTEGRITY=PASS`,
`TRUST_BASIS=EXPLICIT_LOCALLY_INSTALLED_KEY` and
`OFFLINE_REVOCATION_STATUS=NOT_CHECKED`.
The report's `OFFLINE_FRESHNESS` value remains independent of the
signature validity. If the package has expired, signature verification
may still be correct, but the command returns status **3** and the
material must be treated as **stale**.

**Important:** Copying a public key from the same machine only demonstrates
the mechanics of signing and verification. It does not validate genuine
publisher identity, independent distribution or compromised-key recovery.

## Tests

```bash
python -m unittest discover -s tests \\
  -p 'test_offline_evidence_package_v3.py' -v

python scripts/audit_project_completeness.py
```

Tests cover valid and stale signatures, tampering with ZIP or signed data,
unknown or mismatched publisher keys, future signing times, insecure
private-key permissions and refusal to replace signed evidence.

## Operator acceptance — 25 October 2026

The operator successfully verified the signed synthetic development package
against a public key explicitly installed in the local trusted-publisher
directory:

```text
OFFLINE_PACKAGE_SIGNATURE=PASS
OFFLINE_PACKAGE_INTEGRITY=PASS
TRUSTED_PUBLISHER_KEY_ID=443a5010aaf6750db1775c18bd19dc36c53a43c540866ccf301d3bff2864e447
OFFLINE_FRESHNESS=WITHIN_REVIEW_WINDOW
TRUST_BASIS=EXPLICIT_LOCALLY_INSTALLED_KEY
OFFLINE_REVOCATION_STATUS=NOT_CHECKED
OFFLINE_REVIEW_SUBMISSION=DISABLED
PRODUCTION_RELEASE=BLOCKED
```

This confirms **local Ed25519 signature verification** and v2 package
integrity against the installed development public key. The operator did
not provide the focused v3 test-suite output or evidence of independent
publisher identity validation on a different device; neither is claimed
here. A trusted-key file installed locally does not by itself establish
organisational identity, revocation currency or clinical correctness.

## Revocation and security limitations

An offline recipient cannot learn that a trusted signing key has been
revoked since the last trust-store update. The demonstration verifier
reports this honestly as `OFFLINE_REVOCATION_STATUS=NOT_CHECKED`.
A compromised key could sign malicious synthetic packages until the
recipient removes its trust. For any operational deployment, specify an
authorised trust-list owner, publisher identity proofing, trust-list version,
signed revocation updates, maximum offline age, key rotation and recovery.

A digital signature does not make false or stale numbers true, nor does
it approve a malaria investigation. The package remains synthetic and
requires a human reviewer. Offline authenticated decisions and safe
synchronisation are **future, separately evaluated work**.

**Release gate:** This implementation does not resolve Keycloak's
outstanding OpenJDK CVEs or independent production-security review.
