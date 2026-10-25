# AfyaEvidence — project completeness and inconsistency audit

**Audit date:** 25 October 2026. **Branch:** `work/keycloak-live-acceptance` (draft PR #4). This is a repository/source and operator-evidence audit, not a fresh execution on the user's WSL host or independent security certification.

## Verification update — 25 October 2026, latest operator run

Following explicit Node.js 24 activation, the operator reports **264 tests
passed in 60.056 seconds**, `IDENTITY_WORKER_TESTS=PASS`, and
`python -m pip check` returning *No broken requirements found*.
The same full fixture verification confirms 15 synthetic snapshots,
16 independent evaluation cases, 32 scripted agent executions across
standard and CPU profiles, six H-MEM checks, isolated wheel execution
and exclusion of evaluator keys and source data.

The verified output directory is
`runtime/identity-verification-20261025T055816480085Z`.
The wheel `afyaevidence-0.1.0-py3-none-any.whl` was 71,013 bytes,
SHA-256 `492adc0da825403d7eb90740c45f9c6072a83b957fcfa0effe6a49c3a634c8bb`.
The previous failed 259-test run remains legitimate audit evidence of
a Node **22.23.2** execution environment and must not be deleted.
The launcher now records active Node version and blocks incompatible
versions before running the suite. The older **244-pass** baseline is
superseded by this 264-pass operator report.

The successful checks are still **local operator evidence**. Live Zetaris,
Ollama and H-MEM were explicitly NOT_RUN in this invocation, while
hosted CI, independent container-security review and deployment approval
remain outstanding. `PROJECT_RELEASE=BLOCKED`.

## Live Keycloak realm evidence — 25 October 2026

The operator completed the read-only Keycloak Admin REST configuration audit
successfully: `KEYCLOAK_LIVE_REALM_AUDIT=PASS`. One OTP required
action was enabled, none were default actions, and one OTP-related
execution appeared in the selected browser flow. All four realm-level
theme fields returned `DEFAULT_OR_UNSPECIFIED`; the realm registered
14 provider components. This **closes the basic realm-configuration
inspection gate**, but not the Keycloak extension filesystem inventory,
nested-flow reachability, precise affected OpenJDK 2D method analysis or
independent vulnerability assessment. The admin token was not shared or
saved to Git, and the local report remains under ignored `runtime/`.

`CVE_2026_91415=OPEN`, `CONTAINER_SECURITY=BLOCKED_BY_REPORTED_CVES`
and `PROJECT_RELEASE=BLOCKED`.

## Container provider/theme inventory — 25 October 2026

The operator reports matching results from two independent read-only
inspections of the existing Keycloak container: `PROVIDER_JARS=0`,
`THEME_DIRECTORIES=0`, `CUSTOM_THEME_FILES=1`, and
`REALM_DATA=NOT_READ`. The fresh run returned
`KEYCLOAK_EXTENSION_AUDIT=PASS`, with its ignored report at
`runtime/security/keycloak-extension-inventory-20261025T073703Z.json`.
The earlier report was retained. These results fulfil the **limited
container provider/theme directory inventory**, not an audit of all
built-in providers, dynamic code paths or the single unidentified theme
file. The previously observed 14 realm provider components are not
custom JAR counts. The independent OpenJDK applicability and release
security gates remain open.

## Full verification acceptance — 25 October 2026

The operator subsequently reran the integrated verification after the
managed-worker permission-test correction, with the following results:

- **309 regression tests in 63.475 seconds — OK**, no failures.
- `IDENTITY_WORKER_TESTS=PASS`, including v4 publisher-registry regressions.
- `SYNTHETIC_REPRODUCIBILITY=PASS`, **15 snapshots**.
- `SYNTHETIC_EVALUATION=PASS`, **16 cases**.
- Standard and CPU agent profiles both **PASS**; **32 fixture executions**.
- H-MEM reference, persistence, provenance, scope isolation, chronology
  and outbox retry all **PASS**.
- `RUNTIME_PACKAGE=PASS`, isolated scripted profiles `standard,cpu`;
  evaluator keys and source data **not included** in the wheel.
- Python dependency audit: **No broken requirements found**.
- Verification output folder:
  `runtime/identity-verification-20261025T100155156005Z`
- Built wheel SHA-256:
  `416e05b79ab488ef5bffabdc0ceeef253689ae27177907069ead51c319ef0442`.

These are **operator-reported local acceptance outcomes**, not a hosted
CI success or independent security assurance. Live Zetaris, Ollama model
and live H-MEM calls were **not run** in these fixture checks. The
standalone v4 registry CLI rotation/revocation acceptance remains
distinct from tests of that logic. Historical failed verification
evidence is preserved. Production release and Keycloak CVE gates
remain **BLOCKED**.

## Managed-worker permission test correction — 25 October 2026

The operator's latest full regression produced **308 tests, one failure**
in `test_managed_worker.ManagedWorkerTests.test_private_directory_required`.
The test used `mkdir(mode=0o755)` and assumed the resulting directory
was group/other accessible. Earlier development signing commands used
`umask 077`; POSIX directory creation masks requested mode by the
process umask, so the actual result can be `0700`. The
`private_state()` production implementation already rejects
group/other permissions and remains unchanged.

The test now applies `chmod(0o755)`, asserts the actual mode is
`0755`, verifies that `private_state()` raises `Blocked` and
checks it did not silently change the directory permissions.
A complementary test checks that an explicit `0700` directory
is accepted. This removes the environment-sensitive false failure
without relaxing the worker's security boundary.

The corrected full suite **has not yet been rerun by the operator**;
the historical failed run and existing verification logs must be
retained. Production acceptance remains blocked independently of
this test correction.

## Summary

AfyaEvidence is a working **synthetic evidence-review prototype**, with local verification across source inspection, fixture generation, agent orchestration, H-MEM, authenticated review, isolated human dispositions and systemd-managed workers. **Production and clinical release are not authorised.**

### Evidence matrix

| Workstream | Evidence observed | Remaining condition |
| --- | --- | --- |
| Data and source contracts | Fictional six-facility aggregate schema; 15 reproducible snapshots and 16 independent scenarios reported PASS | Real data governance/access and scope-specific acceptance |
| Investigation agent | 32 scripted executions in standard and CPU profiles reported PASS | Repeat live end-to-end verification per intended deployment |
| H-MEM | Reference integrity, persistence, provenance, chronology and outbox checks reported PASS | Production storage/security and real embedding evaluation |
| Local review | Historical accepted revision one preserved; hash-bound receipt evidence and human disposition implemented | Do not imply clinical approval |
| Identity | Three Keycloak roles passed PKCE signature, introspection and role checks; viewer/admin denied review, reviewer made one auditable synthetic disposition | Dedicated operational identity proofing and provider lifecycle at deployment |
| Availability | An otherwise valid access token received HTTP 503 while provider offline; a logged-out session token received HTTP 401; recovery passed | Multi-host failover and production monitoring |
| Managed worker | Real systemd containment and synthetic managed run reported PASS | Deployment service account, resource sizing, reboot and rollback drill |
| Regression and packaging | 244 Python tests, fixture evaluation, H-MEM and isolated wheel PASS (operator-reported, 25 October 2026) | Hosted CI, reproducible dependency lock, artifact signing/SBOM |
| Python dependencies | Local pip 26.2.2, `pip check` clean, `pip-audit` 0 findings reported | Repeat on deployment lock/image |
| Keycloak container | Candidate rescanned with OS and Java DB enabled | OpenJDK CVE-2026-91403 and CVE-2026-91415 remain reported |
| Documentation | Root README rewritten; operator guidance linked and source-evidence bounds explicit | Editorial review of third-party upstream README intentionally deferred |

### Inconsistencies addressed in this integration branch

1. The root README previously stated that the authenticated UI/worker were unimplemented and combined live access permanently blocked by Zetaris login. Those statements predated later operator acceptance and were replaced with precise, scoped historical evidence and outstanding conditions.
2. The identity implementation guide still required `nbf` unconditionally although live Keycloak tokens omit it and the signed `iat` compatibility fix was tested. Clarify the optional `nbf` interpretation and that JWT temporal checks remain in force.
3. Earlier Keycloak setup guidance said `LIVE_KEYCLOAK=NOT_RUN`. Later live tests passed; retain the original guide as procedural instructions but add dated operator evidence and current remaining gates rather than silently rewriting historical instructions.
4. Generic Trivy cross-vendor severity logging was previously confused with a scanner failure. Severity source was inspected; 92 candidate findings used Red Hat severity ratings. Scanner findings themselves are not suppressed.
5. A distinct candidate image has the listed fixed CA-certificate package but unchanged OpenJDK RPM. Separate the *supported certificate mitigation* from the still-open OpenJDK advisories; do not claim vulnerability closure without independent vendor review.
6. The Docker development container's past exit code 255 is not root-caused; subsequent service recovery passed. Do not describe the cause as known.
7. README inventory includes `bridges/hmem/upstream/README.md`, a **pinned upstream reference**. This is not an original project README. It is intentionally unchanged to preserve upstream provenance and the reference hash/integrity contract. The project-owned root README is in UK English. Upstream wording must not be silently edited to meet house style.

### Candidate identity-check correction (25 October 2026)

The first pinned-image inspection incorrectly compared the locally reported
manifest digest against the registry configuration digest. An intermediate
fix also escaped a Bash `printf` format twice, producing a literal
`\\n` instead of a newline and falsely rejecting a matching repository
digest. The operator captured both failures. The comparison now reads each
repository digest as an exact Bash string, requires the immutable pinned
repository reference and checks that Docker's reported image ID matches one
of the independently recorded manifest/configuration digests. Regression
tests cover the two valid ID representations and reject absent, malformed or
different digests. The candidate itself and its realm have not been changed.

**Verification:** the corrected script and new mocked-Docker regression
tests have been committed, but the operator has not yet run this latest
revision. The certificate and OpenJDK 2D checks are still unverified.

### Regression verification update — 25 October 2026

The operator reported `Ran 244 tests in 54.111s; OK`, together with
`IDENTITY_WORKER_TESTS=PASS`. The same verification reported 15 reproducible
synthetic snapshots, 16 independent evaluations, 32 scripted agent
executions (standard and CPU), all six H-MEM reference checks, and
`RUNTIME_PACKAGE=PASS` with evaluator keys and source data excluded
from the isolated wheel. The built wheel was 71,013 bytes with SHA-256
`e9a87a7b3cd0dffc899a4c7c6bd03da334a198dc9d44c13e6372870055365809`.
The operator's verification directory was
`runtime/identity-verification-20261025T050214671866Z`.

These are reproducible local test reports, **not** independently witnessed
hosted CI or live Zetaris/Ollama/H-MEM integration for this command. The
report explicitly states `LIVE_ZETARIS=NOT_RUN`,
`LIVE_MODEL=NOT_RUN` and `LIVE_HMEM=NOT_RUN`. The most recent
pinned-image trust-store and Java module inspection results have not yet
been supplied, so that release gate remains incomplete.

### Engineering issues still requiring attention

- **Security:** CVE-2026-91403 is reported critical on the unchanged OpenJDK RPM, notwithstanding the system CA-store mitigation evidence; CVE-2026-91415 remains high/affected, with no fixed version supplied in the candidate Trivy report. Neither is silently waived.
- **Operational:** Keycloak is a development container. Its production TLS/reverse proxy, pinned base-image/OS lock, secrets rotation, service isolation, backup/restore, vulnerability monitoring and controlled migration have not been accepted.
- **Review process:** Independent code/security review and hosted CI were not completed. Automated local PASS does not supersede either.
- **Evidence:** Full local tests and live PKCE results are operator-reported. GitHub comments record them, but GitHub CI did not independently execute the supplied test logs.
- **Clinical:** Only synthetic malaria data have been approved for these local technical tests; human review is not clinical approval, and there is no real-world disease-surveillance validation.
- **Source provenance:** Retain vendored H-MEM README and pinned source integrity; record third-party licence/provenance review before redistribution.
- **Licensing:** Confirm an explicit licence for original AfyaEvidence code before public reuse; do not infer it from the repository being publicly accessible.

## Repeatable acceptance commands

Use Terminal 1 for the **running** identity API (if a live check needs it); Terminal 2 for tests. A full suite does not require a live provider:

```bash
cd "$HOME/afyaevidence-keycloak-live"
source "$HOME/.venvs/afyaevidence-identity/bin/activate"
source "$HOME/.nvm/nvm.sh"
nvm use 24
export PYTHONPATH="$PWD/src"
python -m pip check
python scripts/verify_identity_worker.py --fixtures
python scripts/audit_project_completeness.py --json "runtime/completeness-audit.json"
bash -n scripts/check_keycloak_java_exposure.sh
bash scripts/check_keycloak_java_exposure.sh
```

**Trust-store test limitation:** Listing certificates or observing module presence is read-only evidence, not a proof of exploitability/non-exploitability. If `keytool` is missing from the minimal image, record BLOCKED instead of installing software inside the candidate image. Do not repeat immutable synthetic review submissions.

**Release decision:** `RELEASE=BLOCKED`. A competent independent reviewer must assess CVE applicability, artefacts, controlled deployment configuration and any signed risk exception. No automatic merge or clinical/production approval.
