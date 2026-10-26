# Offline v4 rotation and revocation — CLI acceptance

This is a reproducible **real subprocess/CLI** acceptance of the v4
root-signed publisher registry against **previously prepared synthetic
fixture evidence**. It complements the 309 locally passing integration
tests, which included v4 unit tests but did not yet demonstrate a
complete command-line rotation ceremony.

## Safety and provenance

The runner deliberately **does not use existing private keys**, the
Keycloak realm, review databases, or the historical v2/v3 files. It
accepts the existing, successful fixture/scripted synthetic receipt
**read-only**, uses `TemporaryDirectory` to create three new
owner-only development Ed25519 key pairs, and produces a fresh ZIP,
two detached signatures and two signed registry versions.
The disposable keys and temporary package are removed automatically
when the runner exits. No secrets are written to Git or printed.

The CLI exercises a complete sequence:
1. Generate independent registry root, original publisher and successor
   publisher development keys.
2. Rebuild a fresh, checksum-valid synthetic v2 ZIP and verify it.
3. Create root-signed registry **v1**, sign with the original publisher
   and successfully verify the signature and registered identity.
4. Create root-signed registry **v2**, register the new key and revoke
   the original key.
5. Confirm the old signature is refused against v2 and the recipient's
   persistent revocation floor records the rejected key.
6. Sign the same synthetic ZIP using the successor key and successfully
   verify using registry v2.
7. Confirm that reverting the recipient to registry v1 is blocked.
   No historic signature, original evidence or review is changed.

All subprocess status markers and exit codes are asserted; an unexpected
success on a negative check is **a test failure**.

## WSL commands — Terminal 2

Terminal 1 may remain stopped. After switching to the latest draft branch:

```bash
cd "$HOME/afyaevidence-keycloak-live"
git fetch origin
git switch --detach origin/work/keycloak-live-acceptance
source "$HOME/.venvs/afyaevidence-identity/bin/activate"
export PYTHONPATH="$PWD/src"

# First compile the implementation and acceptance test without execution.
python -m py_compile \\
  scripts/accept_offline_v4_rotation.py \\
  scripts/offline_publisher_registry_v4.py \\
  tests/test_offline_v4_cli_rotation.py

# The focused test checks Python AST parsing and an actual CLI round trip.
python -m unittest discover -s tests \\
  -p 'test_offline_v4_cli_rotation.py' -v

# Explicit operator acceptance using the already verified synthetic receipt.
python scripts/accept_offline_v4_rotation.py \\
  --receipt runtime/offline-demo-receipt.json
```

Expected final markers:

```text
V4_CLI_ROTATION_ACCEPTANCE=PASS
V4_INITIAL_PUBLISHER=PASS
V4_REGISTRY_V2=PASS
V4_REVOKED_OLD_KEY=BLOCKED_AS_EXPECTED
V4_NEW_PUBLISHER_SIGNATURE=PASS
V4_REGISTRY_ROLLBACK=BLOCKED_AS_EXPECTED
V4_OLD_KEY_REVOCATION_FLOOR=PASS
V4_DISPOSABLE_KEYS=REMOVED_AFTER_EXIT
V4_OFFLINE_REVIEW_SUBMISSION=DISABLED
PRODUCTION_RELEASE=BLOCKED
```

**Do not mark acceptance PASS until the operator supplies the actual
output.** The runner's syntax and CLI integration must be validated by
the execution above. The script was inspected against the existing
v2/v3/v4 command-line argument contracts prior to hand-off.

## Operator-reported acceptance — 25 October 2026

The standalone real-CLI acceptance runner has now completed successfully.
The operator reported the following terminal outcomes:

```text
V4_CLI_ROTATION_ACCEPTANCE=PASS
V4_INITIAL_PUBLISHER=PASS
V4_REGISTRY_V2=PASS
V4_REVOKED_OLD_KEY=BLOCKED_AS_EXPECTED
V4_NEW_PUBLISHER_SIGNATURE=PASS
V4_REGISTRY_ROLLBACK=BLOCKED_AS_EXPECTED
V4_OLD_KEY_REVOCATION_FLOOR=PASS
V4_OFFLINE_REVIEW_SUBMISSION=DISABLED
PRODUCTION_RELEASE=BLOCKED
V4_DISPOSABLE_KEYS=REMOVED_AFTER_EXIT
```

This establishes the operator's **local operational v4 rotation and
revocation PASS** using the disposable, synthetic CLI workflow. The
previous integrated regression milestone was 309 tests PASS; these
new CLI acceptance tests were introduced after that historical run.
Their focused test-output count, subsequent full regression and
hosted CI acceptance should therefore be recorded separately rather
than inferred from the standalone acceptance marker.

The success does **not** prove independent publisher identity vetting,
online revocation freshness, secure root-key custody, trusted-clock
assurance, deployment hardening or clinical authorisation. Production
release remains blocked.

## Limits

The exercise uses a development trust root and synthetic reporting
evidence. It proves the implemented **local trust and revocation
mechanics**, not publisher identity verification in a real organisation,
secure hardware storage, trusted time or remote revocation freshness.
Recipients offline for longer than their registry validity window must
fail closed. Offline review/approval and data synchronisation remain
disabled. Production release and open Keycloak security findings
remain blocked.
