# Offline Evidence Packages v2 — integrity-checked, read-only copies

AfyaEvidence supports a **portable, self-contained offline package** for a
previously prepared *synthetic fixture/scripted investigation*. This second
slice adds a ZIP manifest, file-level SHA-256 integrity checks, a restricted
evidence extract, a review-by date and a local verifier. It does **not** make
the Keycloak-authenticated review application or live Zetaris investigations
offline-capable.

The package is a single ZIP file intended for local storage or an authorised
copy to another computer. It contains exactly three files:

| File | Purpose |
| --- | --- |
| `manifest.json` | Format, snapshot/receipt identity, creation/review-by dates, file lengths and SHA-256 hashes |
| `briefcase.html` | Standalone, read-only HTML briefing; no network resources, scripts or form controls |
| `evidence.json` | Restricted synthetic interpretation, deterministic metric facts and cited evidence identifiers; **no raw source records** |

## Building and verifying

Use a *new* successful receipt, or the earlier verified
`runtime/offline-demo-receipt.json` when it exists. The exporter refuses
failed receipts, live data, real model modes, reviewed/approved status,
missing citations and numerical statements which disagree with the
host-generated deterministic metrics. Existing output paths are never
overwritten.

```bash
cd "$HOME/afyaevidence-keycloak-live"
source "$HOME/.venvs/afyaevidence-identity/bin/activate"
export PYTHONPATH="$PWD/src"

python scripts/offline_evidence_package_v2.py create \\
  --receipt runtime/offline-demo-receipt.json \\
  --output runtime/offline-evidence-package-v2.zip \\
  --valid-hours 48

python scripts/offline_evidence_package_v2.py verify \\
  --package runtime/offline-evidence-package-v2.zip
```

The verifier checks the exact file-name allowlist, archive limits,
duplicate/unexpected members, hashes, synthetic-only policy, required
human-review boundary and timestamps. It reports
`OFFLINE_PACKAGE_INTEGRITY=PASS` only after all checks succeed.

**Stale-data handling:** The HTML always displays a warning that evidence
may be stale, plus the UTC package creation and review-by times. A static
HTML page cannot update its freshness indicator automatically without
running code. Use the Python verifier to obtain an accurate
`OFFLINE_FRESHNESS=WITHIN_REVIEW_WINDOW` or `OFFLINE_FRESHNESS=STALE`
based on the current clock. **STALE does not mean the hash failed**:
an intact old package is still old evidence and should not inform a
current public-health decision.

For offline viewing, copy the ZIP locally, extract only the expected
`briefcase.html` file using an archive manager, and open it in a browser.
No Keycloak, Zetaris, Ollama or network access is required at viewing
time. Keep the original package to repeat integrity verification.

## Verifying a package received from another computer

SHA-256 file checks ensure that the package contents agree with the
*included* manifest. An attacker could alter both the package and the
manifest; therefore these hashes do **not** establish the sender's
identity. If a trusted sender provides the complete ZIP SHA-256 through an
independent channel, verify it explicitly:

```bash
python scripts/offline_evidence_package_v2.py verify \\
  --package runtime/offline-evidence-package-v2.zip \\
  --expected-sha256 <trusted-64-character-sha256>
```

If no independent expected hash is available, the verifier reports
`AUTHOR_AUTHENTICITY=NOT_VERIFIED_UNSIGNED_PACKAGE`. Do not claim
digital signing, PKI verification or secure provenance of an untrusted
download. This version uses checksum-based integrity checks; a real
signature and trusted publisher key policy are a future security gate.

## Acceptance and adversarial tests

```bash
python -m unittest discover -s tests \\
  -p 'test_offline_evidence_package_v2.py' -v

python scripts/audit_project_completeness.py
```

The v2 tests cover an intact package, stale package, changed HTML,
incorrect trusted SHA-256, unexpected/path-traversal archive members,
unsupported live or approved receipts, and refusal to replace a file.

When offline: open the extracted `briefcase.html`, turn Chrome DevTools
Network to **Offline**, force a reload, confirm there are no external
requests and confirm the investigation remains visibly **awaiting human
review**. Do not claim a browser reload PASS until it has been observed.

## Signed distribution follow-up

The [v3 guide](OFFLINE_EVIDENCE_PACKAGES_V3.md) adds detached Ed25519
publisher signatures with a recipient-managed trusted-key directory.
It does not replace v2's structural and checksum verification, nor does
it automatically trust public keys distributed with an unknown ZIP.

## Boundaries

No raw patient records, live district extracts, browser credential
storage, service worker, OAuth tokens, H-MEM notes, offline reviewer
decisions, outbound requests or synchronisation queue are exported.
A fixed review-by interval is **not** a substitute for clinical judgement
or a verified data freshness policy. Local ZIPs are **not encrypted**;
limit their distribution to authorised synthetic demonstration materials.

Before any production-grade offline workflow, design authenticated
signatures, encryption and authorised local access, expiration/revocation
behaviour, service-worker updates, audit logs, conflict-safe sync and
verified one-time replay. The existing OpenJDK CVE and independent release
gates remain blocked.
