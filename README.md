# AfyaEvidence

AfyaEvidence is an evidence-led investigation assistant for **synthetic district-level malaria reporting**. It brings reporting data, transparent calculations and cited findings together so a human reviewer can investigate unusual changes without mistaking an automated explanation for an approved public-health decision.

The application does **not** diagnose patients, declare outbreaks, prescribe treatment, approve investigations on behalf of a reviewer or change source records.

## Project status

AfyaEvidence has progressed beyond its original data-access prototype. The repository now contains a bounded agent, reproducible synthetic evidence, a pinned H-MEM reference bridge, human-review workflows, an identity-aware API and a systemd-managed worker. The live Keycloak integration uses browser-based authorisation-code login with PKCE and strict access-token verification.

Local acceptance evidence was reported by the operator in October 2026:

| Area | Evidence | Boundary |
| --- | --- | --- |
| Automated regression | 264 tests passed on the Keycloak integration branch (operator report, 25 October 2026) | Tests are not an independent security review |
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
