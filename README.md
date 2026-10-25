# AfyaEvidence

AfyaEvidence is an evidence-led investigation assistant for **synthetic district-level malaria reporting**. It brings reporting data, transparent calculations and cited findings together so a human reviewer can investigate unusual changes without mistaking an automated explanation for an approved public-health decision.

The application does **not** diagnose patients, declare outbreaks, prescribe treatment, approve investigations on behalf of a reviewer or change source records.

## Project status

AfyaEvidence has progressed beyond its original data-access prototype. The repository now contains a bounded agent, reproducible synthetic evidence, a pinned H-MEM reference bridge, human-review workflows, an identity-aware API and a systemd-managed worker. The live Keycloak integration uses browser-based authorisation-code login with PKCE and strict access-token verification.

Local acceptance evidence was reported by the operator in October 2026:

| Area | Evidence | Boundary |
| --- | --- | --- |
| Automated regression | 319 tests passed in 60.570 seconds, including v4 real-CLI rotation and security-evidence audit regressions (operator report, 25 October 2026) | Local tests are not hosted CI or an independent security review |
| Synthetic evaluation | 15 reproducible snapshots; 16 evaluated scenarios; 32 scripted agent runs across standard and CPU profiles | Live Zetaris and Ollama were **not** invoked by those fixture checks |
| Memory | H-MEM reference, persistence, provenance, scope, chronology and outbox retry checks passed | The reference embedding approach remains a prototype |
| Human review | Verified individual reviewer identity and append-only review events | The historical local-operator decision remains an unverified legacy identity |
| Local access control | Live Keycloak viewer and administrator reviews denied; reviewer allowed a one-time disposition on a disposable synthetic run | No clinical approval; no repeat review of the accepted investigation |
| Identity resilience | Provider outage returned 503 for a previously valid token; a token was rejected with 401 after test-session logout | Only the documented local tests were exercised |
| Worker supervision | Real systemd containment, cleanup and a synthetic managed execution passed | Not a multi-host queue or production deployment |
| Packaging | Isolated wheel, evaluator/source-data exclusion, fixture runs and local Python dependency audit passed | Container-image and release assurance remain separate |

**Release status: blocked.** The candidate Keycloak image still has reported OpenJDK vulnerabilities, including CVE-2026-91403 and CVE-2026-91415. Independent security review, hosted CI, dependency locking, dedicated service-account hardening, disaster recovery and deployment acceptance are outstanding. Pull requests #1–#4 are intentionally unmerged; this branch is an integration candidate, not the production default.

See [the project completeness audit](docs/PROJECT_COMPLETENESS_AUDIT.md) and [Keycloak residual security assessment](docs/KEYCLOAK_RESIDUAL_SECURITY.md) for evidence and unresolved decisions.

## Get started safely

Work in a separate branch or worktree. Keep local credentials, Keycloak secrets, Docker volumes, JDBC drivers, SQLite review databases and live receipts **out of Git**.

For Ubuntu/WSL with Python 3.12+ and Node.js 24:

```bash
cd "$HOME/afyaevidence-keycloak-live"
source "$HOME/.venvs/afyaevidence-identity/bin/activate"
source "$HOME/.nvm/nvm.sh"
nvm use 24
node --version  # Must report v24.x; Node 22 cannot run the pinned H-MEM bridge
export PYTHONPATH="$PWD/src"

python scripts/verify_identity_worker.py
python scripts/verify_identity_worker.py --fixtures
python scripts/audit_project_completeness.py --json runtime/project-audit.json
```

The full verification command now checks the active Node.js version before running tests. A shell using Node 22 is reported as `NODE_PREFLIGHT=BLOCKED_NODE_24_REQUIRED`, not as a set of unrelated H-MEM test failures. Activate Node 24 with `nvm use 24` in **each fresh terminal** before verification. Do not relax the memory bridge's Node requirement.

Fixture tests do not require live health data, Zetaris access or Ollama inference. The documented Keycloak tests require an explicitly configured local HTTPS provider and private credentials; they should only use disposable synthetic review data.

The local identity-review API binds to loopback only and checks a signed, audience-bound RS256 access token, roles and live introspection. It is a **resource server**, not an interactive production login service or a replacement for production TLS.

## Offline capability: read-only evidence briefcases

AfyaEvidence's deterministic synthetic analysis and scripted agent run locally.
A new [offline evidence briefcase](docs/OFFLINE_EVIDENCE_BRIEFCASE.md) can export a
**previously completed synthetic investigation** as a self-contained HTML page.
It remains readable without a network connection, authentication service,
Zetaris or local model at viewing time. It contains no source records, tokens,
review forms or synchronisation capability. A normal Keycloak-authenticated
browser session and any new live Zetaris investigation **are not offline-first**
at this stage.

This deliberately narrow slice is suited to a truthful low-connectivity
demonstration. It is not a substitute for online identity verification or
human review. The output is a read-only copy and does not grant clinical
authority, new data access or an offline approval mechanism.

### Portable evidence packages v2

The [v2 offline evidence package](docs/OFFLINE_EVIDENCE_PACKAGES_V2.md)
bundles a synthetic read-only briefing, a deliberately restricted evidence
extract and a SHA-256 manifest in one locally stored ZIP. The verifier checks
contents and reports whether its stated review-by time has passed. The offline
HTML continues to warn that a disconnected copy may now be stale.

The v2 package is **unsigned**, so hashes do not establish the publisher's
identity without a separately trusted expected package hash. It does not
cache authentication, collect new Zetaris data, submit offline review
decisions or synchronise changes. This is an offline-read demonstration
rather than a production offline-first system. Local v2 ZIP integrity and
offline browser rendering have been demonstrated; a complete recorded
forced-reload acceptance and hosted verification are separate gates.

### Signed offline packages v3 (development slice)

The [v3 signed-distribution guide](docs/OFFLINE_EVIDENCE_PACKAGES_V3.md)
explains how to apply an Ed25519 detached signature to the existing
read-only synthetic v2 ZIP and verify it against an **explicitly installed
trusted public key**. The signing private key stays outside Git.
Verification checks the v2 package's contents and SHA-256 hashes
before accepting its signature. It reports stale packages and
honestly labels offline revocation status as unchecked.

A valid signature identifies a key trusted by the local recipient,
not an automatically verified healthcare organisation or an approved
public-health assessment. No authenticated offline review, live
source refresh or synchronisation is introduced. The operator reported
successful signed-package verification and 12 passing v3 security tests;
independent publisher identity and production approval remain outstanding.

### Publisher trust registry v4 (development slice)

The [v4 registry guide](docs/OFFLINE_EVIDENCE_PACKAGES_V4.md)
introduces a separately trusted Ed25519 root, signed publisher-key
registries, key rotation, revocation, version/rollback checks and a
maximum 72-hour offline trust age. It checks signed v3 synthetic
packages and never grants offline approval or clinical authority.

An offline verifier knows revocations **only as of the last registry
it has received**. Recipients still require a trusted clock, a
protected registry state and a separately authenticated root public
key. This developer implementation is not a production revocation
service. The v4 tests passed within the operator-reported 309-test local
suite; an independently witnessed CLI registry rotation/revocation
exercise and production release controls remain outstanding.

### v4 rotation and revocation CLI acceptance

The [v4 CLI acceptance runbook](docs/OFFLINE_V4_ROTATION_ACCEPTANCE.md)
provides a disposable-key, end-to-end demonstration: v1 trust
verification, publication of a successor key with old-key revocation,
newly signed package verification and rejection of the old signature
and registry rollback. It creates only synthetic temporary evidence
and does not modify previously signed packages, reviews or Keycloak.
The runner has its own regression tests and Python syntax preflight.
Operator execution and production security clearance are distinct gates.

### Hosted CI and security readiness

The [hosted CI and security readiness audit](docs/CI_AND_SECURITY_READINESS.md)
records a GitHub Actions failure that occurred before any runner or
job steps were assigned, the workflow's independent Python matrix
checks, and a read-only local dependency/Trivy evidence capture.
The latest locally reported 312-test suite passed, but hosted CI
remains failing and its external startup cause is not yet established.
Python dependencies are not fully hash-locked or vulnerability-cleared.
Keycloak CVE and production-security gates remain blocked.

## Investigation contract

For a fictional district, two reporting months and an observation cutoff, AfyaEvidence collects aggregate reporting evidence, compares canonical and raw diagnostics, identifies report revisions and prepares a source-linked brief for human consideration.

Its initial synthetic contract covers six fictional facilities, January 2024–December 2025 and three source tables. There are 144 expected facility-months, with additional raw revisions possible. Evidence is immutable once imported for review; a reviewer disposition does not convert the candidate into clinical approval.

## Technical guides

| Area | Documentation |
| --- | --- |
| Architecture and source boundaries | [Architecture](docs/ARCHITECTURE.md), [Data contract](docs/DATA_CONTRACT.md), [Runtime analysis](docs/RUNTIME_ANALYSIS.md) |
| Agent decisions and models | [Bounded agent loop](docs/AGENT_LOOP.md), [CPU verification](docs/CPU_VERIFICATION.md) |
| Reproducible evidence | [Synthetic data](docs/SYNTHETIC_DATA.md), [Evaluation](docs/EVALUATION.md) |
| Zetaris and JDBC | [First data access](docs/FIRST_DATA_ACCESS.md), [Three-table verification](docs/VERIFY_SNAPSHOT.md) |
| H-MEM | [Memory bridge](docs/HMEM_BRIDGE.md) |
| Review identity and supervision | [Identity and managed workers](docs/IDENTITY_WORKER_IMPLEMENTATION.md), [Review supervision](docs/REVIEW_SUPERVISION.md) |
| Keycloak testing | [Live acceptance](docs/KEYCLOAK_LIVE_ACCEPTANCE.md), [PKCE smoke test](docs/KEYCLOAK_PKCE_SMOKE.md), [HTTP roles](docs/KEYCLOAK_HTTP_ROLE_ACCEPTANCE.md) |
| Security and release | [Keycloak residual risk](docs/KEYCLOAK_RESIDUAL_SECURITY.md), [Java 2D applicability, reverse references and realm audit](docs/KEYCLOAK_JAVA2D_APPLICABILITY.md), [Project completeness](docs/PROJECT_COMPLETENESS_AUDIT.md), [Implementation backlog](docs/IMPLEMENTATION.md) |
| Supporting references | [Contracts](docs/CONTRACTS.md), [Integration decisions](docs/adr/0001-local-runtime-and-adapters.md), [Source register](docs/SOURCES.md) |

## How to contribute and review

Keep deterministic fixtures and human review separate from live clinical decision-making. Investigations must not generate SQL, execute arbitrary shell commands, mutate source records or automatically approve their own findings. When reporting test results, name the exact environment, revision and scope, and distinguish **PASS**, **BLOCKED** and **NOT RUN**.

Use UK English for documentation and commit descriptions where practical. Keep writing clear, considerate and specific, without claiming production readiness from local successes. The repository's licensing and provenance obligations must be reviewed before reuse or redistribution of code and dependencies.
