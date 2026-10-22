# Authenticated local review and supervised worker (development slice)

This branch is based on PR #1 at `0fd52a1`. It does **not** merge PR #1,
constitute deployment approval or validate the October 22 live receipt.
It adds a loopback-only review surface and a separate child-process supervisor.

## PR #2 engineering corrections — 22 October 2026

This section supersedes the verification status of the historical entries below.
The operator-reported starting baseline was 162 tests in 35.261 seconds and an
empty job audit. Neither pull request has been merged.

### Changes and migration contract

- Review schema version 2 adds `execution_json` and `provenance_status` in a
  transaction. Existing receipt hashes, candidate/evidence JSON, timestamps,
  revisions and review rows are preserved. The migration reads the original
  receipt only when its bytes match the stored SHA-256 and its identity,
  snapshot and content match the imported record. Missing or changed originals
  produce explicit `legacy_unavailable`, `legacy_hash_mismatch` or
  `legacy_content_mismatch` states. No analysis `not_run` field is used to infer
  execution. Exact re-import can recover missing provenance; conflicting
  content cannot. Future schema versions are rejected.
- The API exposes top-level data/provider/model/memory/profile, execution
  bounds, counters and available verification fields. The dashboard displays
  these modes separately from analysis evidence. Receipt claims are hash-bound
  provenance, not signed attestations or an independent live verification.
- Imports bind both Run ID and resolved receipt path to the original bytes.
  Identical retries are idempotent; changed bytes, another path for the same
  ID, or another ID for the same path fail explicitly without replacing rows.
- Review retries bind the event key to reviewer, expected revision, decision
  and reason. Concurrent writers are serialized; reads use a consistent
  snapshot for the current revision and history. One disposition remains final.
- The HTTP body cap is 32,768 bytes, accommodating a 2,000-character reason
  even when every non-BMP character uses JSON surrogate escapes. The existing
  trimmed 10–2,000-character contract remains enforced. Excess envelope padding
  is still bounded. Malformed/duplicate-key/nonfinite JSON, invalid Unicode,
  ambiguous body framing and unsupported content types fail closed. Host and
  Origin checks reject foreign browser origins; raw request/error logging is
  suppressed and database connections close after requests.
- Linux supervision handles SIGTERM and SIGINT, terminates the complete child
  process group (including descendants after leader exit), waits/reaps, writes
  the final event, then closes worker ownership. A five-second TERM grace is
  followed by KILL. The child inherits the lock descriptor so abrupt supervisor
  death does not immediately free the slot. Unfinished/invalid event records
  independently block replacement until operator reconciliation. Interrupted
  model calls are never automatically replayed. The review bearer capability
  is removed from the worker environment.
- Job audit now rejects malformed final states, incomplete cleanup and orphan
  final records. Package verification explicitly permits the four operator
  modules already shipped on this branch while retaining the strict exclusion
  of evaluator keys, data, credentials and unexpected wheel members.

Migration occurs on the first database connection/import. Stop the old reviewer process and
take a consistent SQLite backup before restarting the updated service in Ubuntu
with the same database and token. Do not submit another disposition to test it.
Do not move/rewrite original receipts to hide a migration conflict. An unavailable
original remains unavailable until its exact original bytes/path can be restored.

### Executed verification

The assistant executed checks in WSL Ubuntu, Python 3.12.3 and Node 24.22.1.
The final full suite ran **178 tests in 68.995 seconds: OK**, with no skips.
Its local log is `runtime/pr2-corrections-final-tests-20261022.log` (gitignored).

| Check | Observed result |
| --- | --- |
| Final full regression run | 178 tests, 68.995 seconds, OK; 16 tests added to the 162-test baseline |
| Initial full regression run | 176 tests, 68.762 seconds, OK; followed by two additional regressions |
| Probe bytes and fixture source contract | PASS; six fixture rows; live JDBC NOT_RUN |
| Synthetic regeneration and independent evaluation | PASS; 15 snapshots and 16 evaluation cases |
| Snapshot verifier and deterministic analysis | PASS; canonical positives 100/100, raw positives 100/120 |
| Pinned H-MEM reference | PASS: persistence, provenance, scope, chronology and outbox retry; mock hash embeddings |
| Scripted agent | PASS: 16 cases × standard/CPU profiles = 32 executions; live model NOT_RUN |
| Built wheel and isolated execution | PASS: package exclusion guard, deterministic CLI and both scripted profiles |
| Existing job audit | `[]`, exit 0; no events altered |
| Existing review DB migration rehearsal | PASS on a temporary SQLite backup in Ubuntu; one run and one review preserved exactly |

The actual backup rehearsal recovered `zetaris / ollama / qwen2.5:1.5b /
hmem_reference / cpu` from the hash-matching original receipt, preserving
`run_a0dfd33e79a14482aca3149bd96aadac`, revision 1 and `accept`. The original
database was opened read-only and was **not migrated**. A Windows backup
rehearsal correctly reported `legacy_unavailable` because the stored Linux
receipt path was unavailable there. This verifies migration behavior, not a
new live Zetaris/Ollama execution or renewed semantic approval.

An earlier native Windows review-test run had two temporary SQLite cleanup
errors caused by existing tests retaining connections; the seven test assertions
otherwise passed. Ubuntu is the supported supervisor target. The complete
Ubuntu run, rather than that Windows attempt, is the local acceptance gate.

### Independent completeness and security assessment

A separate source-and-regression review covered these boundaries; no external
penetration test, formal security-tool scan or independent human audit is claimed.

| Boundary | Finding and acceptance limit |
| --- | --- |
| Authentication/authorization | API reads/writes require bearer capability; empty/short configuration fails, Host/Origin checked. Public loopback page has no record data. Still one shared local capability, without SSO, roles, expiration or rate limiting. |
| Identity/history | Client cannot supply reviewer identity. Server records `local_operator`, not a verified person. Transaction/revision/idempotency regressions pass; direct database administrator writes remain outside this application's immutability guarantee. |
| Provenance/evidence | Exact-byte hash and original-content checks protect imports/migration; missing provenance is explicit. Local operator-controlled receipts are not cryptographically authenticated producer attestations. |
| Concurrent submissions | Competing decisions produce exactly one history row; mismatched actor/revision retries reject. No additional disposition can replace an accepted record. |
| Lifecycle/restart | Real-process tests exercise TERM, INT, timeout escalation, exited leaders, lock contention during cleanup and abrupt KILL. KILL cannot write a final event; manual reconciliation is mandatory. No automatic retry/queue is implemented. |
| Secrets | No credential values added to code/receipts/tests; child logs suppressed, HTTP errors sanitized and review token excluded from worker environment. Authorized JDBC credentials still enter the worker environment; OS account isolation remains necessary. |
| Model/memory isolation | Existing tool allowlist and reference validation remain intact. No reviewer capability is added to agent tools. Scope/cutoff/outbox tests run against pinned H-MEM; historical notes remain untrusted context, never current arithmetic. |
| Failure handling | Existing provider, JDBC and memory failure regressions run; failed live dependencies do not become fixture success. This correction cycle did not rerun live JDBC or inference. |
| Deployment | Local development acceptance only. Hosted CI/deployment smoke, individual identity, operational monitoring and recovery procedures remain outstanding. |

All supervisors must share one trusted local state directory. The Linux
`flock`/subreaper design is not distributed coordination or a hostile-process
sandbox. Descendants deliberately escaping the process group require cgroup
containment in a future service deployment. An uninterruptible kernel process
can keep cleanup/ownership pending; investigate it rather than starting a
replacement. Do not delete unfinished events or locks to force a retry. First
prove old workers are gone, inspect partial receipts, and record an authorized
operator reconciliation; this slice supplies no automated recovery writer.

**Acceptance:** the scoped corrections have local regression evidence; current
browser visual acceptance, hosted CI, deployment acceptance, production
readiness and clinical approval are not asserted. GitHub Actions budget
restrictions remain administrative and separate from application failures;
no hosted PASS or budget bypass is claimed. Recommended next milestone:
individual reviewer identity/authorization plus a service-level cgroup worker
and explicit audited crash reconciliation, followed by controlled deployment
smoke and operational acceptance. Preserve both PRs unmerged for review.

## Review service

Prerequisites: Python >= 3.12, editable project installed; run from repo root.
The reviewer service uses only the Python standard library. Use a fresh high-entropy
token and never commit or paste it into terminal logs.

```bash
python -m unittest discover -s tests -p 'test_review_server.py' -v
python -m afyaevidence.review_server \
  --import-receipt runtime/agent-live-cpu-20261022T080645Z.json \
  --runtime-root runtime \
  --db runtime/reviews.sqlite3
read -rsp 'Review token (32+ characters): ' AFYA_REVIEW_TOKEN; echo
export AFYA_REVIEW_TOKEN
python -m afyaevidence.review_server --db runtime/reviews.sqlite3 --port 8010
```

Open `http://127.0.0.1:8010/` in the **same host's** browser,
enter the token and the `IMPORTED_RUN` shown by the import command,
inspect the frozen candidate and evidence references, and record
one of `accept`, `request_more_evidence`, or `reject` with a reason.

### Boundaries and limitations

- The service rejects unready receipts, missing snapshot IDs, model-issued
  approval and missing semantic review requirements. The original receipt
  is identified by SHA-256, never edited by review actions.
- Bearer authentication is enforced on all API reads/writes; the UI is
  loopback-only. Use a private machine and do **not** put this HTTP listener
  behind an internet-accessible reverse proxy. The token is held in the
  browser tab; this is **not** an identity-provider integration.
- SQLite revisions, `BEGIN IMMEDIATE`, event IDs and append-only review
  rows prevent accidental duplicate/mismatched disposition writes.
- Reviewer identity is the local operator role, **not verified individual
  identity**. The service has no multi-user roles, SSO, MFA or session
  expiration. Consequently, this is a local authenticated proof of concept,
  not production user authentication or regulatory sign-off.
- `accept` records an evidence-review disposition only. It never
  changes source tables, creates an outbreak alert or turns the model
  proposal into clinical approval.
- There is no automatic transfer of historical review notes to H-MEM.
  Separate validated bridge/outbox policy is still required.
- Verify full evidence provenance and substantive interpretation manually
  before choosing a disposition.

## Supervised CLI

The standalone supervisor launches the **existing** agent module in a
separate process, with an external timeout and process-group termination.
It writes start/final job records under the gitignored `runtime/jobs/` path,
and preserves agent receipts.

```bash
python -m afyaevidence.supervisor --timeout 660 -- \
  --data-mode fixture \
  --snapshot data/synthetic/fx_32e8b610 \
  --model-provider scripted \
  --execution-profile cpu \
  --memory disabled_fixture \
  --output runtime/supervised-fixture-001.json
```

This command is a development example, **not evidence that it has run**.
The supervisor has no queuing, distributed lock, heartbeat, restart recovery
or persistent worker service yet. Run only one supervisor at a time.
Credentials should remain in the existing private interactive prompt or
environment; never put them on the command line. Child logs are suppressed
to avoid accidental credential exposure; inspect the preserved receipt and
event records instead.

## Deployment acceptance criteria (not yet met)

1. Execute complete tests on the final commit, including review API
   authentication and invalid-token scenarios.
2. Confirm the live receipt's hash, source provenance, semantic-review
   requirement and model/SQL/memory mode independently.
3. Add authenticated reviewer identity, appropriate roles, session lifecycle,
   CSRF/cookie policy if sessions are introduced, TLS for non-loopback access,
   rate limits and security audit, then penetration/security review.
4. Add a real single-worker claim/queue, cancellation and restart recovery.
5. Verify worker crash/timeout, database integrity, repeated requests,
   inaccessible data modes, stale receipts and manual recovery.
6. Run hosted CI and deployment smoke tests with authorised synthetic
   data and controlled secrets before any production readiness claim.
7. Obtain explicit human assessment of evidence content. There is no
   automated medical or public-health decision.

## Actual combined run

Operator-reported output on 22 October 2026:
`DATA_MODE=zetaris`, `MODEL_MODE=ollama`,
`MEMORY_MODE=hmem_reference`, `EXECUTION_STATUS=ready_for_review`,
`MODEL_CALLS=2`, `TOOL_CALLS=5`, `REPAIRS=0`, and three live
mode PASS summaries. Receipt:
`runtime/agent-live-cpu-20261022T080645Z.json`.
This receipt remains local and has **not** been inspected by this change.
Do not substitute the published CPU fixture receipt for the live one.

## 22 October 2026 observed review verification

Operator supplied the actual review API result for
`run_a0dfd33e79a14482aca3149bd96aadac`:
`{"revision":1,"disposition":"accept","replayed":false}`.
This confirms that a *new* human disposition was accepted by the local
review service. The uploaded evidence showed the synthetic reporting-artefact
case: October/November canonical positives 100/100, raw 100/120,
with two accepted versions for November F001 report R202511001.
The candidate continued to show `semantic_review_required=true` and
`approval=null`. This is **not** a clinical approval, new model
test, reviewer identity validation, deployment check or re-run of source access.

## Updated dashboard and local verification

The dashboard displays the summary, canonical/raw comparison, version
history, matched facility contributions, limitations and audit history.
Expand the technical evidence section to inspect the original identifiers.
Its numeric summary only displays the metric categories explicitly present
in the candidate's numerical statements. Missing values display as dashes;
they must not be silently manufactured. Existing review records remain intact.

```bash
git fetch origin
git switch codex/review-supervision-slice
python -m unittest discover -s tests -v
python -m afyaevidence.review_server --db runtime/reviews.sqlite3 --port 8010
```

Restart the old local HTTP process before launching the updated server.
Keep the same review DB and existing private token. Re-open the imported run;
its review history should show the prior `accept` revision 1, and the
disposition button must be disabled. Do not submit a second review to test it.

The supervisor now uses a Linux kernel `flock` on the shared
`runtime/jobs/.worker.lock`; a second supervisor receives `busy`
instead of starting another model/JDBC worker. This does **not** yet supply
job queueing, heartbeats, recovery orchestration or distributed coordination.
The unchanged existing receipt and review records remain local.

**Verification status:** additions are published to GitHub but tests and
the updated UI have not been executed by the assistant against the user's
Ubuntu runtime. Require a clean local regression run and a fresh hosted CI
result before promoting the draft PR.

## Local regression evidence and follow-up hardening (22 October 2026)

User-provided complete Ubuntu log: **156 tests ran in 33.408 seconds; OK**.
This is the verified baseline for commit `019088a4`, not an assertion that later additions have passed.
The log includes the new review dashboard, immutable history and review-service tests.
The authenticated dashboard was also observed loading the accepted synthetic run.

Subsequent changes on this branch:

- Monthly comparison reads authoritative `evidence.metrics` values rather than requiring
  the model-selected brief to cite tested/positivity facts. Only `available`, finite,
  numeric, canonical/raw, all-available comparison/target metrics are displayed;
  unavailable measurements remain dashes, never converted to zero.
- Real localhost HTTP regression tests cover missing/incorrect bearer tokens, authorised
  reads, review submission, idempotent retries and duplicate rejection.
- Worker tests cover exclusive file lock contention, failed-child event persistence
  and invalid entrypoint/existing receipt validation. These are test doubles,
  not proof of crash recovery or actual Ollama/JDBC worker lifecycle.

Run the complete suite again on the updated branch:

```bash
python -m unittest discover -s tests -v 2>&1 | tee runtime/review-hardening-local-tests.log
```

Check the output's final `Ran N tests ... OK`, and verify the dashboard shows
canonical `tested_total=500` and `positivity_pct=20` for both months.
The old accepted review is immutable: no second submission is needed.

GitHub Actions has shown immediate workflow failure before populated steps;
operator reports an account budget block. Until a billing notice is directly
inspected, describe it as **consistent with administrative blocking**, not a
confirmed application test failure or a hosted CI PASS. No budget bypass,
CI relaxation or manual success status is appropriate.

For production use, strong individual reviewer authentication and authorisation,
CSRF policy when appropriate, rate limits, controlled audit retention,
TLS and non-loopback security review, robust worker recovery and operational
monitoring are still outstanding.

## Latest completed local regression gate — 22 October 2026

After the deterministic metric-display change and new HTTP and worker tests,
the operator reported this exact local `unittest discover` summary:

```text
----------------------------------------------------------------------
Ran 160 tests in 34.642s

OK
```

**LOCAL_REGRESSION=PASS (operator-reported).** This applies to the branch's
current verification cycle at commit `a5511c3` subject to the operator's
local checkout; the output alone does not establish the exact Git SHA or
Python executable. It includes the added HTTP and worker unit tests, but
is not evidence of a deployed authenticated identity provider or a real
process-crash recovery test. The previous 156-test baseline remains preserved.

**Browser display acceptance is still pending** for the metric correction.
The expected immutable stored state is review revision 1 / disposition
`accept`, with canonical tested totals 500 / 500 and positivity percentages
20 / 20. Do not submit an additional disposition for the existing run.

The GitHub Actions administrative budget restriction is reported by the
operator, but no GitHub billing notice was examined in this record. Hosted
CI is not considered PASS. The PR remains unmerged pending further review.

## Final dashboard acceptance and follow-up hardening

The operator's 22 October 2026 browser screenshot **confirmed** the full
synthetic investigation panel displayed the corrected values:

| Metric | October 2025 | November 2025 |
| --- | ---: | ---: |
| Canonical positives | 100 | 100 |
| Raw diagnostic positives | 100 | 120 |
| Canonical tested | 500 | 500 |
| Canonical positivity | 20% | 20% |

Six matched facility rows, revision history and the disabled repeat-disposition
control were also visible. **LOCAL_DASHBOARD=PASS**. This complements the
operator's `160 tests in 34.642s: OK` log for the prior code state.
Neither proves clinical approval.

Additional hardening committed *after* that local run:

- Review POST requests now reject foreign `Origin` values (403) and
  non-JSON content types (415). This protects the local bearer-token
  write endpoint but is not a substitute for production authentication.
- `python -m afyaevidence.job_audit --state-dir runtime/jobs`
  examines preserved job start/final event pairs. An absent final event
  becomes `needs_operator_reconciliation`, **not** automatic restart,
  failure rewriting, or success. Exit status is nonzero when reconciliation
  remains outstanding.
- Regression tests cover missing/corrupt job events and preservation of
  previous records. These newer tests have **not** been included in the
  previously reported 160-test PASS.

Acceptance steps for the new commit:

```bash
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
python -m unittest discover -s tests -v 2>&1 | tee runtime/review-hardening-final-tests.log
python -m afyaevidence.job_audit --state-dir runtime/jobs
```

A nonzero audit exit with unfinished historical jobs is expected and should
trigger manual investigation, not deletion. Do not overwrite or re-submit
the accepted review. The protected API remains loopback-only.
Production-grade reviewer identity, per-role authorisation, full worker
recovery/queue, cancellation, load tests and secured deployment remain
unimplemented and must be independently accepted.
