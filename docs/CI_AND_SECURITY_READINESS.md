# GitHub Actions and security readiness — 25 October 2026

## Hosted workflow diagnosis

The draft PR #4 head before these repairs (`0dc624a`) had a failed
pull-request-triggered GitHub Actions run **40184584707**. GitHub reported
a failed `fixture-contract (3.13)` job in about two seconds, with
`runner_id=0` and **no steps**. Python 3.12 and 3.14 matrix jobs were
cancelled, also with no assigned runner or steps. Earlier runs had a
similar pattern. GitHub job logs could not be retrieved from the
connected API.

These facts are consistent with a **pre-runner scheduling, account,
Actions policy or infrastructure issue**. The precise cause is not
proven. There is no evidence that a Python test or dependency
installation ran in the failed job. Do **not** change application
security policy or mark code tests failed solely from this metadata.

### Workflow correction

The `.github/workflows/probe.yml` matrix now uses `fail-fast: false`,
so a genuine failure on one Python version does not automatically
cancel its peers. A toolchain identity step reports Python, Node.js
and pip versions *if the runner actually starts*, and `pip check`
executes after the contract tests.

The workflow retains explicit, SHA-pinned checkout/setup actions,
Node 24 and Python 3.12/3.13/3.14. Checkout credentials are not persisted.
The workflow deliberately uses synthetic fixture data and does not
require a JDBC endpoint, live model, production Keycloak or a private
key. Do not add real secrets to these PR checks.

### GitHub-side action needed

Inspect the [latest failed run](https://github.com/buriro-ezekia/afyaevidence/actions/runs/40184584707)
through the GitHub interface, especially any organisation/repository
billing, spending limit, Actions policy, runner availability or
account-level restriction banner. If GitHub exposes the actual failure
reason, preserve it verbatim in PR #4. Retry the workflow only once
the external restriction is understood. If jobs still have zero
assigned runners and zero steps, no local Python change can establish
a hosted CI PASS.

## New matrix diagnostic after correction

After setting `fail-fast: false`, GitHub recorded run
**40185459313** for the amended integration branch on 25 October 2026.
All three matrix jobs (`fixture-contract (3.12)`, `(3.13)`,
`(3.14)`) returned `failure`; each had `runner_id=0`,
`steps=[]`, and an approximately **two-second** run duration.
This confirms the jobs no longer cancelled one another, but none
started on a runner. The Python test suite, toolchain reporting and
dependency checks **did not execute in hosted CI**. The exact
GitHub-side restriction or infrastructure failure remains unknown.

Run: https://github.com/buriro-ezekia/afyaevidence/actions/runs/40185459313

Check repository **Settings → Actions → General**, relevant billing
or usage limits and any workflow-run banner/error shown in the Actions
UI. The operator should copy the first available GitHub-side error
message without credentials. A workflow YAML or Python security
relaxation is not justified by this pre-runner failure.

## Python dependency review

The project core declares no runtime Python dependencies. The optional
identity feature requires `PyJWT[crypto]>=2.13.0,<3` and
`cryptography>=46.0.4`; packaging build uses
`setuptools==84.0.0`. These are **version constraints**, not a
fully reproducible, hash-locked, vulnerability-reviewed deployment
dependency graph.

The operator's recent full **312-test** suite and `pip check` passed.
This establishes local compatibility, not freedom from known CVEs
or equivalence of the three CI interpreter versions. The new
`scripts/audit_security_evidence.py` records installed version
identities, `pip check`, a supplied pre-existing Trivy report, the
scan's SHA-256 and all critical/high findings. It does **not** query
vulnerability databases, run a fresh Python vulnerability scan, update
dependencies, or attest scanner DB freshness.

## Keycloak pinned candidate — unresolved security gate

Previously inspected Linux/AMD64 candidate:

```text
quay.io/keycloak/keycloak@sha256:3e1ac632e743660017b1e6bb4c3ffc800fd02c82cdd0db858cd03456a98a8dfc
```

Last operator Trivy candidate report: **1 critical, 1 high, 55 medium,
35 low**. The development running container uses a distinct image ID.
The candidate must not silently replace the running realm.

Current Red Hat advisories were checked on 25 October 2026:

- `CVE-2026-91403` — certificate-chain/trust issue. Red Hat notes that
  nonportable RHEL OpenJDK RPMs consume the system `ca-certificates`
  fix. Prior local fixed-package/symlink checks support this mitigation,
  but independent root-certificate and chain review remains incomplete.
  Source: https://access.redhat.com/security/cve/cve-2026-91403
- `CVE-2026-91415` — OpenJDK Java 2D/font-processing issue. The
  candidate's `java.desktop` module is present and its Keycloak path
  reachability has not been independently excluded.
  Source: https://access.redhat.com/security/cve/cve-2026-91415

**Neither advisory is cleared by this work.** Do not remove relevant
certificates, patch the running container opportunistically, downgrade
scanner severities or disable security tests.

### Read-only local audit

Terminal 2, Node 24 not required for the following standalone script:

```bash
cd "$HOME/afyaevidence-keycloak-live"
source "$HOME/.venvs/afyaevidence-identity/bin/activate"
export PYTHONPATH="$PWD/src"

python -m py_compile scripts/audit_security_evidence.py
python -m unittest discover -s tests -p 'test_security_evidence.py' -v

python scripts/audit_security_evidence.py \\
  --trivy-report runtime/security/keycloak-candidate/candidate-trivy.json \\
  --out runtime/security/keycloak-security-evidence-20261025.json
```

A new output filename is required if that destination already exists.
The script fails closed for an absent/incomplete scanner inventory,
unknown candidate manifest, unavailable installed dependencies or
inconsistent pip environment. It cannot verify the scan is a fresh
Docker rescan; its input is explicitly an existing report.

For a **new** pinned candidate scan, rerun the existing documented
read-only image checks and Trivy scan against the exact digest,
preserving the old report for comparison. Vendor applicability evidence,
a patched image, a security review and production deployment controls
must all be evaluated independently.

## Security audit diagnostic follow-up — 25 October 2026

The operator ran the original security-audit command and received:

```text
SECURITY_AUDIT_EVIDENCE=BLOCKED_INCOMPLETE_INPUT
CONTAINER_RELEASE=BLOCKED
```

The previous implementation grouped missing files, invalid Trivy JSON,
incomplete package inventory, missing Python dependencies and I/O
errors into a single message. The auditor now emits a constrained
`SECURITY_AUDIT_REASON` code and the requested `TRIVY_REPORT_INPUT`,
while preserving the failed status. Tests cover missing and malformed
reports. This is **a diagnostic improvement, not evidence of a clean
Trivy scan**.

Before rescanning or renaming any evidence, locate the exact existing
candidate report by filename under the ignored `runtime/security`
directory:

```bash
find runtime/security -maxdepth 5 -type f \\
  \\( -iname '*trivy*.json' -o -iname '*candidate*.json' \\) -print

python -m py_compile scripts/audit_security_evidence.py tests/test_security_evidence.py
python -m unittest discover -s tests -p 'test_security_evidence.py' -v
```

If a valid prior Trivy JSON report is found, run the audit with that
**exact path**, using a fresh destination filename. Its provenance must
still be independently matched to the pinned AMD64 candidate: the
`--image-manifest` option is an operator-supplied assertion rather than
an automatically checked image identity. Do not substitute the scan
for the *different running development image*, or treat a missing
report as zero vulnerabilities.

If no report exists, report `TRIVY_CANDIDATE_REPORT=MISSING` and keep
security acceptance blocked until a fresh, pinned, complete scan is
performed. Preserve prior reports, existing Docker/Keycloak state and
all accepted review records.

## Local dependency inventory blocker — 25 October 2026

The operator confirmed that the existing candidate Trivy file
`runtime/security/keycloak-candidate/candidate-trivy.json` is present,
but the initial audit stopped with
`SECURITY_AUDIT_REASON=required_python_dependency_not_installed`.
The original audit required three installed distributions: `PyJWT`,
`cryptography` and `setuptools`. However `setuptools==84.0.0`
is specified under `[build-system]` in `pyproject.toml` and is
installed in a separate isolated environment for a standard pip wheel
build, not necessarily in the active venv.

The revised read-only audit requires `PyJWT` and `cryptography` as
identity runtime dependencies, records a missing `setuptools` as
`NOT_INSTALLED_ISOLATED_BUILD_DEPENDENCY` rather than treating it as
a runtime error, and reports the package versions. Missing required
runtime dependencies continue to block the audit with their names
listed. This change does not modify `pyproject.toml`, install
packages, suppress CVEs or relax pip dependency checks.

The operator also observed `Permission denied` when `find`
traversed Trivy's private cache/`fanal` directories; both expected
candidate JSON reports were nevertheless listed. These cache traversal
messages are not evidence of Trivy scan corruption.

After a syntax and focused regression check, rerun the audit with
the candidate's existing JSON and a **new** output filename. Do not
use the report for the separate running development container, and do
not treat `SECURITY_AUDIT_EVIDENCE=PASS` as container clearance.

## Operator acceptance — successful local security-evidence audit

The operator subsequently reported `SECURITY_AUDIT_EVIDENCE=PASS` from
the existing pinned-candidate Trivy JSON. The audit counted **562**
package inventory entries and **92 vulnerabilities**: 1 critical,
1 high, 55 medium, 35 low and 0 unknown. The two tracked findings
`CVE-2026-91403` and `CVE-2026-91415` remain **REPORTED**.

The observed Python environment was `PyJWT=2.15.1`,
`cryptography=50.0.2`, and
`setuptools=NOT_INSTALLED_ISOLATED_BUILD_DEPENDENCY`.
`PYTHON_PIP_CHECK=PASS` confirmed dependency consistency; a Python
vulnerability scan was explicitly `NOT_RUN`. The audit wrote
`runtime/security/keycloak-security-evidence-v3.json`. The
`CANDIDATE_MANIFEST` value was
`sha256:3e1ac632e743660017b1e6bb4c3ffc800fd02c82cdd0db858cd03456a98a8dfc`,
an expected candidate identity in the audit contract, **not a new
Docker image identity attestation or fresh scan**.

This closes the *local read-only evidence collection* gate only.
`CONTAINER_RELEASE=BLOCKED` and `PRODUCTION_RELEASE=BLOCKED`
remain explicit. The new security-audit focused test-suite result
has not been supplied independently with this output.

## Acceptance statuses

| Gate | Status |
| --- | --- |
| Local synthetic regression (312 tests) | OPERATOR_REPORTED_PASS |
| v4 CLI rotation/revocation | OPERATOR_REPORTED_PASS |
| Hosted GitHub Actions | FAILED_BEFORE_STEPS_CAUSE_UNKNOWN |
| Python runtime constraints | DOCUMENTED_NOT_HASH_LOCKED |
| Python CVE scan | NOT_RUN |
| Candidate Trivy inventory | HISTORICAL_FINDINGS_RECORDED |
| OpenJDK CVE resolution | BLOCKED |
| Independent security review | PENDING |
| Production release | BLOCKED |
