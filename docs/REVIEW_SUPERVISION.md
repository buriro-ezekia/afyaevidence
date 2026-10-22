# Authenticated local review and supervised worker (development slice)

This branch is based on PR #1 at `0fd52a1`. It does **not** merge PR #1,
constitute deployment approval or validate the October 22 live receipt.
It adds a loopback-only review surface and a separate child-process supervisor.

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
