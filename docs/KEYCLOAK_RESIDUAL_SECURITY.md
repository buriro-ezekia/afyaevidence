# Keycloak container security — residual risk and decision record

**Status (25 October 2026): not approved for production.** This record separates facts observed in local tests from scanner findings, vendor guidance and unresolved assumptions. It is not an independent penetration test or risk-acceptance signature.

## Image identity and scope

The running *development* Keycloak container still uses image configuration `sha256:79c623a22abacf3fe6c00a5fb30f5b7843d717b234033b80995891c06116d244` for `quay.io/keycloak/keycloak:26.8.1`. A separately downloaded pinned Linux/AMD64 candidate uses manifest `sha256:3e1ac632e743660017b1e6bb4c3ffc800fd02c82cdd0db858cd03456a98a8dfc` and configuration `sha256:b55801be6ce15109868bd056dc18d62d47106bfaad7ffbd1a5d804192ec98257`.

The two configuration digests differ. The candidate has **not** replaced the running container or shared its realm data volume. The candidate was scanned using Trivy with Java analysis enabled after Docker Scout's Java DB download failed. A candidate scan eventually completed, reporting 1 critical, 1 high, 55 medium and 35 low findings, all 92 sourced to Red Hat. The following findings are material; their scanner status is not an independent exploitability conclusion.

| Advisory | Previous local image | Pinned candidate | Decision |
| --- | --- | --- | --- |
| CVE-2026-114406 | Critical, `ca-certificates` with old package | No longer reported; fixed package `2026.2.92_v9.0.319-90.3.el9_8` installed | Candidate package-level remediation supported |
| CVE-2026-91403 | Critical, `java-21-openjdk-headless` | Critical, under investigation, no OpenJDK fixed version reported | Mitigation hypothesis supported by Red Hat; independent confirmation needed |
| CVE-2026-91415 | High, `java-21-openjdk-headless` | High, affected, no fixed version reported | Remains open; no verified exposure exclusion |

## CA trust-store evidence and limitations

The candidate links `/etc/pki/java/cacerts` to `/etc/pki/ca-trust/extracted/java/cacerts`; the system TLS bundle resolves to `/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem`. Both linked files exist and are nonempty. The candidate contains the Red Hat fixed version of `ca-certificates`.

Red Hat's CVE-2026-91403 statement says non-portable RHEL OpenJDK RPMs use the system CA certificate store and that removing the affected root certificates is sufficient to address this particular flaw. These facts are **consistent with a mitigation** for this RHEL image. They do not establish that the installed trust contents lack every problematic eMudhra certificate, nor do they overrule the unresolved OpenJDK vulnerability record.

Use `bash scripts/check_keycloak_java_exposure.sh` in the Keycloak worktree to inspect the pinned candidate with no network access, including a Java keytool name check. The script cannot provide definitive certificate-chain analysis; aliases and subject names vary. A negative text match **must not** be interpreted as proof of remediation. Vendor attestation or certificate-chain review is required for closure.

## Candidate certificate-name inspection — 25 October 2026

The operator subsequently ran the corrected pinned-image inspection. It
confirmed the manifest/repository digest, Java trust-store symlink and
successful `keytool -list -v`. The broad subject-name check returned
`EMUDHRA_ROOT_MATCH=FOUND_REQUIRES_REVIEW`. **Do not classify this as a
mitigation pass or as proof that the specific vulnerable root remains
trusted.** A text match alone does not identify the certificate uniquely;
inspect alias, entry type, full subject, SHA-256 fingerprint and chain.
The script now emits those metadata fields for matching trust-store entries.
This updated diagnostic is committed but has not yet been executed on the
operator's host. A previous `NOT_FOUND` result was invalid because the
read-only container could not create a Bash here-string temporary file.

The same read-only probe reported `JAVA_DESKTOP_MODULE=PRESENT`, confirming
that the headless RPM includes the Java desktop module. This is relevant to
CVE-2026-91415 but cannot establish remote reachability.

Both residual advisories remain **open**. Obtain vendor evidence and
independent application-level review before considering a mitigation
exception.

## Exact certificate identity and vendor-chain clarification — 25 October 2026

The operator completed the pinned, read-only candidate `keytool` metadata
inspection. Exactly **one** broad eMudhra subject-name match was returned:
alias `emsignrootca-g1`, entry type `trustedCertEntry`, subject
`CN=emSign Root CA - G1, O=eMudhra Technologies Limited, OU=emSign PKI, C=IN`,
SHA-256 certificate fingerprint
`40:F6:AF:03:46:A9:9A:A1:CD:1D:55:5A:4E:9C:CE:62:C7:F9:63:46:03:EE:40:66:15:83:3D:C8:C8:D0:03:67`.
The exact fingerprint is independently listed for emSign Root CA - G1 by the
CA's public repository, and **must not be conflated with emSign ECC Root CA - G3**.
The public Mozilla disclosure of the compromised intermediate keys stated
there was no evidence that *all* eMudhra roots were compromised.

**Important remaining verification:** the broad eMudhra-name filter did
**not** assess a separately named, cross-signing root such as
`AAA Certificate Services` / `Comodo AAA Services root`. Red Hat security
bulletin `RHSB-2026-012` expressly identifies the Comodo AAA Services root
and emSign ECC Root CA - G3 as relevant roots. Mozilla's incident
communication also names emSign Root TLS CA - G3 as a potential chain.
Check all these exact roots and any cross-signed versions by certificate
fingerprints/trust status, not solely string matches on eMudhra.

Evidence strengthens the applicability of the corrected
`ca-certificates` package, but **does not close CVE-2026-91403** until
these chain checks and vendor review are complete. Keep
`CVE-2026-91415` separately open: `java.desktop` is present, while
application-path reachability is unverified. Do not remove certificates
or alter the running container during this assessment.

References:
- https://access.redhat.com/security/vulnerabilities/RHSB-2026-012
- https://seclists.org/oss-sec/2026/q4/233
- https://repository.emsign.com/

## Follow-up: 118 Java trust-anchor subjects reviewed — 25 October 2026

The operator used an isolated, network-disabled, read-only pinned candidate
to list certificate subjects in `/etc/pki/java/cacerts`. The complete command
reported `TRUST_STORE_SUBJECTS=118` and
`CERTIFICATE_CHAIN_SUBJECT_CHECK=PASS`. None of the subjects contained the
tested names `emSign ECC Root CA - G3`, `emSign Root TLS CA - G3`,
`AAA Certificate Services` or `Comodo AAA Services`. The earlier broad
eMudhra match was the distinct trusted `emSign Root CA - G1` fingerprint
recorded above.

**Evidence-based assessment:** This supports Red Hat's documented system
CA-store mitigation for the trust-related CVE-2026-91403 alongside the
installed fixed `ca-certificates` package and verified Java CA symlink.
Subject matching is not a definitive fingerprint- or chain-validation audit;
it does not prove the absence of a renamed or cross-signed anchor, an
application-specific trust store or an alternate certificate validation path.
The operator explicitly reported
`CERTIFICATE_CHAIN_TRUST_ASSESSMENT=INCOMPLETE`. Keep the scanner advisory
visible and seek independent vendor/security review before an exception is
authorised.

This inspection does **not** address OpenJDK 2D vulnerability CVE-2026-91415:
`java.desktop` is present and its reachable Keycloak application paths are
not independently assessed. Both findings remain recorded and production
release stays blocked.

## OpenJDK 2D exposure — CVE-2026-91415

Red Hat describes a flaw in OpenJDK 2D processing where crafted input reaching an exposed API may cause denial of service or limited data access/modification. The candidate continues to contain `java-21-openjdk-headless 1:21.0.12.1.1-1.2.el9`. Being headless does **not** prove `java.desktop` or Java 2D APIs are absent, nor does using Keycloak primarily for authentication prove those paths are unreachable.

The pinned image inspection reports whether the JDK lists the `java.desktop` module. This is an **availability indicator, not a reachability proof**. An independent review must inspect the precise vulnerable call sites and Keycloak's relevant HTTP, theme, image, extension and library paths. Do not declare `not affected` based only on lack of observed graphics processing.

## Keycloak 26.8.1 Java 2D application path — source review

The tagged 26.8.1 implementation includes an OTP QR-code generation route:
`TotpUtils.qrCode()` supplies a fixed 246×246 QR code request to
`QRCodeUtils.encodeAsQRString()`, which uses ZXing's
`MatrixToImageWriter.writeToStream(..., "png", ...)`.
This is a concrete Keycloak server-side **graphics-generation** path, not
proof that attacker-controlled **font rendering** reaches the affected
OpenJDK vulnerability. The pinned image contains `java.desktop`, and the
installed OpenJDK still reports CVE-2026-91415 as affected. The specific
font API, upstream patch and untrusted-input reachability remain unverified.

See [the focused applicability assessment](KEYCLOAK_JAVA2D_APPLICABILITY.md)
and its optional offline pinned-image JAR reference inventory. Do not use
module presence, JAR class references or functional OTP checks to declare
the CVE non-exploitable. Production approval remains blocked.

## Controls and outstanding evidence

Local provider testing used loopback HTTPS with an explicitly trusted development certificate, three separate application-role accounts, short-lived signed tokens, mandatory online introspection, and a read-only authenticated-outage test. The operator observed HTTP 503 during provider unavailability and HTTP 401 after logout of a previously accepted token. This is **development acceptance**, not evidence of hardened public deployment.

Required before any production risk decision:

- Vendor security guidance and fixed-package/errata tracking for both OpenJDK advisories.
- Independent assessment of the actual Java trust contents and 2D input reachability.
- Rescan a patched, pinned image with full OS and Java package inventory; compare all critical/high findings, not only named CVEs.
- Isolated candidate migration and rollback drill on a copy of the realm (never use the current live development volume as a trial).
- Independent code/security review, dependency/OS/container policy checks, dedicated service account and TLS deployment checks.
- Documented reviewer approval from an authorised security owner; no model-generated approval.

**Decision:** `CONTAINER_SECURITY=BLOCKED`; `PRODUCTION_RELEASE=BLOCKED`; no clinical approval. PR #4 and predecessor PRs remain unmerged.

## Primary references

- Red Hat: https://access.redhat.com/security/cve/cve-2026-91403
- Red Hat: https://access.redhat.com/security/cve/cve-2026-91415
- Red Hat: https://access.redhat.com/security/cve/cve-2026-114406
- Trivy: https://trivy.dev/docs/latest/guide/scanner/vulnerability/

## Hosted CI and current security readiness audit — 25 October 2026

The [CI and security readiness record](CI_AND_SECURITY_READINESS.md)
separates the failed-before-steps GitHub Actions workflow from actual
code-test outcomes, and provides a read-only audit of installed Python
versions and the last pinned candidate Trivy report. **No new
candidate rescan or production security clearance is claimed.**
