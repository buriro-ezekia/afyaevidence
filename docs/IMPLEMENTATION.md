# Ordered GitHub implementation backlog

> **Current implementation note (25 October 2026):** The issue breakdown below
> is the original development backlog, not a statement that the review and
> identity slices are still unimplemented. Later work on draft PRs #2–#4
> introduced loopback review, verified OIDC identities, Keycloak PKCE,
> SQLite audit grants and systemd managed workers. The operator reported
> 232 passing tests, live three-role authentication, provider-outage
> rejection, session logout invalidation and a supervised synthetic job.
> Release is **still blocked** by unresolved Keycloak OpenJDK advisories,
> independent security review, hosted CI and deployment acceptance.
> See [the completeness audit](PROJECT_COMPLETENESS_AUDIT.md).
>

Status: implementation is on `codex/architecture-and-jdbc-probe`, with PR #1 open. Issues 01–04 have their previously recorded operator/live and local acceptance evidence. Issue 05 now includes the explicit two-request CPU profile, finite phase contracts, smaller prompts and reserved brief time. Actual Ollama CPU inference passed with fixture data; the current combined Zetaris/Ollama/H-MEM check is BLOCKED at JDBC login, with failed receipts retained. No combined success or Issue 05 completion is claimed from fixture or scripted tests. See [CPU verification](CPU_VERIFICATION.md) and [agent loop](AGENT_LOOP.md). Worker, authenticated review API/UI and release evaluation slices remain planned.

Use short feature branches and focused pull requests into `main`. Record each PR's behaviour, limitations and actual checks. If available on the account, configure the main branch to require CI and review; the architecture pack does not claim those protections exist.

## Issue 01: project-data access spike

**Priority:** P0. **Depends on:** none. **Target:** first half-day.

- Inspect the working Ubuntu/JDBC setup without changing Docker storage or reinstalling Zetaris.
- Use the supplied JAR/class and resolve its actual absolute location. Verify Java and Python bridge compatibility; retain local credentials outside Git.
- Choose a supported staging/registration route using the current instance and official guide. Inspect existing objects before reusing names; keep project sources out of Zetaris's internal metadata PostgreSQL database.
- Prove one tiny synthetic project table, then three source reads and a non-multiplying join. Compare values, row counts and a version-aware aggregate with a hand-calculated reference.
- Record SQL feature/parameter-binding/timeout support honestly. Store the tested setup recipe and a sanitised receipt. SELECT 1 is retained as a separate connection check.

**Done when:** actual project rows and expected aggregate results are retrieved through Zetaris. Missing data access is a blocking integration issue, not something the UI conceals. If a route fails, document it and try one supported alternative before broadening implementation.

## Issue 02: package, source contracts and deterministic generator

**Priority:** P0. **Depends on:** Issue 01 for live setup; generator can proceed in parallel. **Target:** day 1.

- Create the Python package/CLI, reviewed dependency lock, local configuration model and CI without sponsor secrets.
- Generate six fictional facilities, 24 months and three CSVs with fixed seed/timestamps. Publish exact byte hashes and canonical table-content hashes in a manifest.
- Use opaque dataset IDs. Keep the three core fixtures and mixed/edge variants reproducible; place answer keys only under evaluator paths.
- Validate schema/grain/key constraints, raw version rows and 144 expected facility-months.

**Done when:** regeneration produces identical bytes; the expected scenario arithmetic matches the independent answer key; runtime packaging excludes expected answers.

## Issue 03: immutable snapshots and deterministic analysis

**Priority:** P0. **Depends on:** Issue 02. **Target:** day 2.

- Implement fixture/live gateways behind one protocol, with no automatic fallback.
- Select latest observed versions at a fixed cutoff, preserve withdrawn/invalid/missing findings and validate joins.
- Implement canonical/raw diagnostic/matched-facility views, positivity, count changes, percentage-point differences and coverage metrics.
- Define fact/evidence IDs, exact arithmetic, exclusions and manifest checks.

**Done when:** core and edge calculation cases pass, row ordering does not change results and live source retrieval agrees with the reference for the same immutable batch.

## Issue 04: actual Meterless H-MEM bridge

**Priority:** P0 for sponsor-backed demonstration. **Depends on:** source contracts; can proceed alongside Issue 03. **Target:** days 2–3.

- Pin the reviewed upstream H-MEM reference and its licence/attribution. Lock Node tooling; avoid live-main downloads and copied node_modules.
- Implement the managed JSON-lines helper and typed Python client with fixed operations, timeout/output limits and process cleanup.
- Persist a scoped approved reviewer note, restart, recall it with provenance and show its audit trail. Reject cross-scope/missing-source notes and prevent numeric memory from becoming current evidence.
- Implement the review-outbox receipt/idempotency design and crash-retry test.

**Done when:** actual upstream-reference operations are captured in a receipt; persistence, provenance, scope filtering and retries pass. Clearly disclose mock hash embeddings and prototype storage.

## Issue 05: bounded investigation agent

**Priority:** P0. **Depends on:** Issue 03; integrate real memory after Issue 04. **Target:** days 3–4.

- Probe the actual model endpoint from Ubuntu. Evaluate the installed Ollama model on strict JSON actions. If inadequate, verify an accessible alternate provider rather than assuming model capability from a name.
- Add a separate optional Meterless Runtime adapter only when its authenticated /v1/models and generation checks pass; H-MEM usage does not require that gateway.
- Implement mandatory baseline facts, allowed follow-up tools, fixed scope, budgets, repeated-call guard, explicit errors and one bounded repair.
- Validate metric/evidence refs and render numeric statements deterministically. Preserve semantic uncertainty and competing explanations.

**Done when:** real model-driven tool traces exist for each core scenario, with no fabricated IDs, unsupported numerical claims or approval authority. Scripted mode remains explicitly labelled and cannot satisfy live acceptance.

## Issue 06: API lifecycle and human review

**Priority:** P0. **Depends on:** stable contracts; can proceed after Issue 02 with scripted provider. **Target:** days 3–4.

- Add SQLite migrations, queue claims, supervised worker lifecycle, incremental events, deadline/cancellation handling and interrupted-run recovery.
- Start JDBC only inside the fresh worker process. Test connection cleanup and no JVM fork/reload pattern.
- Implement local sessions, Origin/CSRF checks, review idempotency/revision control and outbox writes.
- Test refusal of direct/model-forged review calls without the browser capability.

**Done when:** explicit human review persists across restart; source data and candidate briefs remain unchanged; duplicate/stale requests behave predictably.

## Issue 07: small review interface and export

**Priority:** P1. **Depends on:** Issue 06. **Target:** day 5.

- Build district/month/cutoff form, status polling, comparison panel, explanation cards, evidence drawer, limitations, review and run history.
- Keep source/provider/memory modes visible and put integration diagnostics in an expandable panel.
- Escape model/source text; show missing values and failures instead of empty success states.
- Export selected synthetic investigation as Markdown and JSON with provenance and review history.

**Done when:** a browser user completes one investigation, traces a claim to records and records a decision without terminal intervention.

## Issue 08: end-to-end evidence and submission package

**Priority:** P0. **Depends on:** all prior live gates. **Target:** day 6, leaving time for submission.

- Run the full evaluation matrix and repeat core/mixed/insufficient scenarios with the declared real model. Preserve failures and blocked/not-run checks.
- Demonstrate live Zetaris -> deterministic facts -> model tools + actual H-MEM -> validated brief -> human review. Include restart/recall evidence.
- Record code revision, dependency/source/data hashes, prompt versions, actual provider/model, cutoffs and timing.
- Write README installation/troubleshooting instructions and a short demo script; verify a fresh checkout can run the stated modes.
- Confirm current event rules, track choice, attribution and pre-existing-work disclosure before submitting. Use the organiser's current event page, not the older dates/rubric in Meterless's community guide.

**Done when:** the source, actual demonstration, limitations and reproducible instructions agree. Fixture checks alone do not establish sponsor-backed completion.

## CI and release checks

Required PR jobs after implementation:

1. Python lint + unit/contract/evaluation tests without external credentials.
2. Node bridge/reference smoke + persistence/scope/provenance/outbox tests on the pinned source.
3. Browser smoke using an explicit fixture/scripted mode, including error/missingness/review paths.
4. Packaging check that credentials, local databases, JARs, runtime evidence and evaluator keys are not included in the application distribution.

Real JDBC and model checks run separately on the user's machine unless a correctly networked authorised runner is deliberately introduced. GitHub-hosted localhost does not reach Docker Desktop on the user's computer. Do not expose local services or add secrets to pull-request runs to work around that boundary.

## Stop points that protect the sprint

If source ingestion is blocked, finish the reference calculations but label integration BLOCKED and resolve data access before UI work. If local model tool-use fails, choose one verified accessible model route; do not add swarms or agents to compensate. If H-MEM setup is blocked, report it separately and avoid claiming Meterless integration from a class name or mock adapter.

Defer climate analysis, real DHIS2 access, forecasting, patient data, automated notifications, multi-user cloud deployment, cross-district memory and source corrections until the scoped investigation path passes.
