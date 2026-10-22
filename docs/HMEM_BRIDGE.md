# Pinned Meterless H-MEM bridge

The bridge executes the actual Meterless reference at commit
`1742dec56a66e58eef9dda2d2b865823758ca8cd`. Its ten TypeScript modules, original package.json module metadata, README and
Apache-2.0 licence are vendored unchanged under `bridges/hmem/upstream`.
`upstream.lock.json` pins their SHA-256 hashes. The copies were also reconciled
against the original Git blob hashes. See `bridges/hmem/ATTRIBUTION.md`.

## Requirements and execution

Use **Ubuntu/WSL**, Python 3.12+ and **Node 24.x in Ubuntu**. Node's
`--experimental-transform-types` executes the original TypeScript, including
constructor parameter properties. The transform is experimental; this adapter
checks Node major 24 and tests the actual engine rather than claiming support for
other versions. No npm package installation, compiler, new model, credentials or
network service is required. Upstream's optional dev dependencies are not copied.

In your existing repository terminal:

```bash
git pull --ff-only origin codex/architecture-and-jdbc-probe
python scripts/verify_hmem.py --doctor
python -m unittest discover -s tests -v
python scripts/verify_hmem.py \
  --analysis runtime/revision-zetaris-analysis.json \
  --output runtime/hmem-verification.json
```

The output path must be new. The supplied analysis receipt is read as historical
provenance; this command makes no new JDBC call and does not invoke a model. It
creates an explicitly synthetic operator-test review note, syncs it through the
actual reference, restarts the helper, recalls/audits it, checks cutoff and
cross-district/family exclusion, and exercises retry after the memory write but
before acknowledging the outbox. Test stores are temporary and removed afterwards.
The JSON receipt records source snapshot/analysis IDs and the supplied analysis
file's SHA-256. This does not constitute a clinical approval or authenticated
reviewer identity. Without `--analysis`, the smoke uses fixture-derived source
provenance and explicitly records that mode.

Expected output:

```text
HMEM_REFERENCE=PASS
HMEM_PERSISTENCE=PASS
HMEM_PROVENANCE=PASS
HMEM_SCOPE_ISOLATION=PASS
HMEM_CHRONOLOGY=PASS
HMEM_OUTBOX_RETRY=PASS
LIVE_MODEL=NOT_RUN
LIVE_ZETARIS=NOT_RUN_THIS_COMMAND
```

If Node 24, source integrity, local storage, provenance or subprocess operation is
unavailable, the check fails visibly. There is no mock-memory or empty-result
fallback. A new empty scope legitimately recalls no notes; an acknowledged
projection that disappears fails validation instead of returning empty success.

## Host integration boundary

`src/afyaevidence/memory.py` exposes three host components:

- `Scope(dataset_family, district_id)` derives an opaque storage-directory key.
  The host fixes the scope; a model cannot pass arbitrary store paths or switch it.
- `ReviewStore` persists a reviewed-note event and pending outbox row in one SQLite
  transaction. Review IDs are idempotent; conflicting reuse is rejected. This is a
  host/operator API for context notes, not a completed authenticated review route.
- `HmemBridge` owns a POSIX `flock` for the scope from before process launch until
  process cleanup. Both recall users and outbox users acquire this same lock.
  SQLite transactions finish before Node I/O. The bridge is Ubuntu/WSL-specific;
  native Windows locking is not implemented.

The bridge launches Node with an argv array and no shell/network listener. NDJSON
requests have request IDs and fixed operation names. Helper operations are
`health`, `remember_reviewed_note`, `audit` and `recall`. Requests and replies are
capped at 64 KiB, notes at 2,000 characters, queries at 1,000 characters, and recall
at three results. A scope permits at most 100 review events/records, with 2 MB
checks on persisted upstream state/ledger files. The smaller protocol envelope may
reject an audit before those larger storage ceilings; that is a visible capacity
failure, not successful truncation. Default request/lock timeout is ten seconds.
The host terminates/kills and reaps the helper, closes pipes and releases the lock
on context exit. Raw helper diagnostics are withheld; stdout is protocol JSON only.

Only **recall** may become model-visible in the subsequent agent slice. The host
write API has no model-tool registration. Note creation requires an existing source
review event; every store record and recall result is rechecked against that event,
including source identity, scope, content, review ID and snapshot/analysis refs.
An acknowledged memory ID must still exist under its original source event. Local
admins can alter SQLite and JSON, so this is inspection support, not cryptographic
protection or proof of an authenticated health professional's decision. Linking
review routes to actual stored investigations remains part of the API/UI slice.

## Outbox, retries and persistence

Reviewed-note events use a stable `afya-review:<review_id>` source. The actual
reference allocates its own `mem-*` IDs. Under the scope lock, the helper checks
that stable source before adding. If Node persisted a note and the caller failed
before saving its SQLite receipt, the next sync finds that note and acknowledges
it rather than adding another. The tests execute that failure window, close the
helper, restart it, retry and verify a single create event.

SQLite review events remain authoritative; reference JSON is a derived projection.
Upstream writes JSON directly rather than atomically replacing it. Startup checks
reject malformed, inconsistent, oversized or missing acknowledged projection state
and missing creation audit records. An incomplete write is visible and may need
operator repair/reconstruction; no automatic destructive reset/rebuild command is
included. A review event persists when memory sync fails, leaving a pending outbox.
This is idempotent projection logic, not an upstream distributed transaction or
exactly-once guarantee across arbitrary crashes/storage faults.

## Scope, chronology and interpretation

The trusted scope is dataset **family** plus district, allowing historical notes
across snapshots of that family while preserving their original snapshot refs.
The reporting-data cutoff and `memory_as_of_utc` are separate inputs. A note is
eligible only when both the review event and actual reference memory creation are
no later than the memory cutoff. Future notes are removed before ranking, not
merely hidden after choosing a top result. The scoped recall view uses the actual
reference store/query implementation with eligible records only; read audit events
are appended to the persistent reference ledger. Python rechecks the result again.

Returned notes carry `role=historical_review_context`, `untrusted=true` and
`current_measurement=false`. They are never inserted into the current metric
catalogue. Embedded instructions remain data; the helper exposes no approval,
source-write, shell, dreaming or automatic conflict-resolution operation. The
current tests establish bridge boundaries, not model resistance to prompt
injection; model-level checks still need to run after the bounded agent exists.

The upstream embedder is a deterministic **mock hash embedder**. Ranking scores
are not calibrated clinical confidence. Storage is local JSON plus an append-only
application ledger, not a production database or tamper-proof audit trail. Actual
H-MEM execution does not establish Meterless Runtime model inference, current
numeric evidence or integrated-agent completion.

## Recorded checks

Local checks on 22 October 2026: **84 tests passed**, including 17 tests that launch
the actual pinned Node/TypeScript reference. Checks cover restart persistence,
source/audit provenance, district/family and temporal isolation, corrupted/lost
projection detection, event idempotency, post-write outbox retry, cross-process
scope contention, killed helpers, request failure, timeout cleanup and untrusted
injected-note labels. `verify_hmem.py` also passed against the actual reference.
The wheel guard and isolated fixture runtime smoke passed after adding the Python
client. The Node helper/upstream remain separate repository integration assets and
must be supplied through the explicit `bridge_dir` when using an installed wheel.
Evaluator code and answer keys remain outside the runtime wheel.

CI installs a pinned setup-node action for Node 24 and runs the actual reference
smoke plus the full suite. The known GitHub Actions account budget/startup block
still prevents claiming hosted validation. The operator's live Zetaris runtime
PASS was reported separately; their own local H-MEM receipt is the next check.
The model, integrated agent, authenticated review UI and deployment remain pending.

## Startup portability and diagnosis

The original upstream `package.json` is now included and hash-pinned. Its
`type=module` makes the TypeScript reference independent of a surrounding CommonJS
checkout. No upstream dependency installation is required. A regression test
launches the actual helper beneath a parent declaring CommonJS.

Run `python scripts/verify_hmem.py --doctor` before repeating a failing full suite.
It checks only fixed Node version/platform metadata, upstream hashes and a fresh
temporary helper handshake. It needs no credentials or analysis receipt. Linux
Node 24 is required inside Ubuntu: a Windows node.exe inherited through PATH does
not satisfy that requirement. Wrong/missing Node versions, source integrity and
lock/protocol errors now retain specific safe messages instead of being replaced
with one generic startup error. Arbitrary driver/helper stderr is still withheld.
A diagnostic PASS does not itself establish note persistence or scope acceptance;
run the full suite and smoke afterwards.
