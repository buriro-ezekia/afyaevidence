# Offline Evidence Packages v4 — publisher trust and revocation

This phase builds on the [signed v3 ZIP](OFFLINE_EVIDENCE_PACKAGES_V3.md)
without changing its bytes, detached signature or existing private keys.
It introduces a **root-signed publisher registry**, a version counter,
publisher identities, key-rotation and revocation rules, an offline
freshness bound and an anti-rollback state file.

The registry is a **development security prototype for synthetic malaria
evidence**. It is not production PKI, an online revocation service or
authorisation to approve public-health decisions.

## Trust model

A separate Ed25519 **root trust key** authorises registry changes.
Recipients must obtain its public key through a separate trusted channel.
A registry is valid only when its signature verifies using that root. It
contains publisher names, Ed25519 public keys, stable SHA-256 public-key
identifiers, validity windows and `active` or `revoked` statuses.

The package's own detached v3 signature is verified using the registry's
currently active publisher key. **Revocation is retrospective in v4**:
a revoked publisher key cannot authenticate *even an older package*
that it signed when still active. A later registry is prohibited from
reactivating keys already recorded as revoked on that recipient.

The registry remains usable offline only within the shorter of its
signed expiry and **72 hours since its issue**. Once that window has
passed, verification fails closed. The v2 package's review-by deadline
is checked independently: an intact, correctly signed but stale package
returns exit code 3.

## Local development-only setup

**Terminal 1 can remain stopped.** Use Terminal 2. Keep all private keys,
signed registries and anti-rollback state outside the Git repository and
never copy key material into chat or a browser screenshot.

```bash
cd "$HOME/afyaevidence-keycloak-live"
source "$HOME/.venvs/afyaevidence-identity/bin/activate"
umask 077

mkdir -p "$HOME/.local/state/afyaevidence-v4-root"
chmod 700 "$HOME/.local/state/afyaevidence-v4-root"

python scripts/offline_evidence_package_v3.py keygen \\
  --private-key "$HOME/.local/state/afyaevidence-v4-root/root-private.pem" \\
  --public-key "$HOME/.local/state/afyaevidence-v4-root/root-public.pem"
```

The generated root private key is **unencrypted and owner-only** in this
development workflow. It must not be used in production; operational
roots require protected custody, approved offline ceremonies, separation
of roles and recovery planning.

The existing v3 signing public key represents a development publisher:

```bash
python scripts/offline_publisher_registry_v4.py create-registry \\
  --root-private "$HOME/.local/state/afyaevidence-v4-root/root-private.pem" \\
  --publisher-public "$HOME/.local/state/afyaevidence-signing/dev-public.pem" \\
  --publisher district_demo \\
  --version 1 \\
  --valid-hours 48 \\
  --output runtime/offline-trust-registry-v1.json
```

A recipient installs **only** the independently authenticated root public
key. The registry file may be transmitted alongside signed evidence,
because it must itself validate against the pre-installed root.

```bash
python scripts/offline_publisher_registry_v4.py verify \\
  --root-public "$HOME/.local/state/afyaevidence-v4-root/root-public.pem" \\
  --registry runtime/offline-trust-registry-v1.json \\
  --state-dir "$HOME/.local/state/afyaevidence-v4-recipient" \\
  --package runtime/offline-evidence-package-v2.zip \\
  --signature runtime/offline-evidence-package-v2.sig.json
```

If your earlier v2 package is past its review-by time, prepare a **fresh
synthetic v2 package and v3 detached signature** first, using new
filenames. Existing packages, signed records and review decisions must
never be overwritten or deleted to make tests pass.

Expected status fields include:

```text
OFFLINE_V4_TRUST_REGISTRY=PASS
PUBLISHER_KEY_STATUS=ACTIVE
OFFLINE_PACKAGE_SIGNATURE=PASS
OFFLINE_PACKAGE_INTEGRITY=PASS
OFFLINE_REVOCATION_STATUS=AS_OF_SIGNED_REGISTRY_ONLY
ONLINE_REVOCATION_FRESHNESS=NOT_VERIFIED
OFFLINE_REVIEW_SUBMISSION=DISABLED
PRODUCTION_RELEASE=BLOCKED
```

## Rotate and revoke the previous publisher key

To demonstrate rotation, generate another **development publisher** key
pair in a new owner-only directory. Retain the first key and registry as
immutable test evidence. The old key ID may be found in the earlier v3
signature under `key_id`; this is a public identifier, not a secret.

```bash
python scripts/offline_publisher_registry_v4.py create-registry \\
  --root-private "$HOME/.local/state/afyaevidence-v4-root/root-private.pem" \\
  --publisher-public "$HOME/.local/state/afyaevidence-signing/rotated-public.pem" \\
  --publisher district_demo \\
  --version 2 \\
  --previous-registry runtime/offline-trust-registry-v1.json \\
  --revoke "<old-public-key-id>" \\
  --output runtime/offline-trust-registry-v2.json
```

After the recipient authenticates v2, the previously signed ZIP must
be **rejected** if its detached signature references the revoked key.
A freshly produced synthetic ZIP signed by the new private key can
succeed while the new key is within its permitted validity window.

## Rollback and equivocation protection

The recipient stores the highest authenticated registry version and its
exact SHA-256, plus the cumulative set of revoked publisher key IDs.
A lower version, a different registry signed at the same version or a
later registry attempting to reactivate an already revoked key is
rejected. Updates are guarded by a local exclusive file lock and atomic
replacement within an owner-only state directory.

**Limits:** A malicious local administrator may delete, restore or edit
the state file; this is not hardware-backed anti-rollback protection.
An offline device with *no existing version floor* cannot know whether
an older but still time-valid registry has been superseded. Keep local
recipient state protected and provision an independently authenticated
minimum version when onboarding real devices. This demo does not yet
provide such an onboarding protocol.

Clock rollback can likewise undermine the freshness window. An
authenticated trusted-time source or trusted hardware clock is required
for stronger deployment assurance. A stolen root key can sign malicious
registries; root rotation and recovery are not implemented by this slice.

## Tests and release boundary

```bash
python -m unittest discover -s tests \\
  -p 'test_offline_publisher_registry_v4.py' -v

python scripts/audit_project_completeness.py
python scripts/verify_identity_worker.py
python scripts/verify_identity_worker.py --fixtures
```

The adversarial tests cover trusted registration, unknown root,
publisher revocation, stale registry rejection, same-version equivocation,
key rotation, local state tampering, and prohibition on reversing a
previously recorded revocation.

The v4 registry **does not provide** offline Keycloak authentication,
safe offline review/approval, queued writes, synchronisation, production
key management, online certificate-status checking or clinical
authorisation. Existing Keycloak OpenJDK vulnerabilities, independent
security review, hosted CI and deployment acceptance remain **BLOCKED**.
