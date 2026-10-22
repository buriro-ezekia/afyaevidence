# Bounded investigation agent

The runtime now has a strict action loop over the verified frozen reporting bundle,
an explicit Ollama adapter, and a separate scripted provider. This slice provides an
operator CLI, not the future authenticated review web application. A candidate is
always awaiting human review; there is no agent approval, source edit, shell,
filesystem, arbitrary SQL or arbitrary network tool.

## Local fixture checks

Use your existing Ubuntu checkout and Node 24 (the root `.nvmrc` records `24`):

```bash
git pull --ff-only origin codex/architecture-and-jdbc-probe
python -m unittest discover -s tests -v
python scripts/check_agent.py
python scripts/run_agent.py \
  --data-mode fixture \
  --snapshot data/synthetic/fx_32e8b610 \
  --model-provider scripted \
  --output runtime/agent-scripted-revision.json
```

Output paths must be new; saved receipts are never overwritten. The fixture check
runs 16 cases across all 15 snapshots and an earlier correction cutoff. Its
`MODEL_MODE=scripted` and `LIVE_MODEL=NOT_RUN` labels are mandatory. The scripted
policy reads tool results and selects reviewed codes; it imports no evaluator,
scenario recipe or expected answer file. Scripted success tests control flow and
reference handling, not model capability.

## Verify the actual model before making another live source query

The configured starting endpoint is the user's existing Ollama service at
`http://127.0.0.1:8082`, with candidate model `qwen2.5:3b`. Reachability from Ubuntu
and that exact installed model remain to be checked. The adapter never starts a
server, downloads a model, scans ports, follows HTTP redirects, uses environment
proxies or silently changes providers. Explicit host configuration is required.

```bash
python scripts/verify_model.py \
  --endpoint http://127.0.0.1:8082 \
  --list-models
```

Then check strict action generation with an actual installed model:

```bash
python scripts/verify_model.py \
  --endpoint http://127.0.0.1:8082 \
  --model qwen2.5:3b \
  --output runtime/model-verification.json
```

If the model name is absent, select an actual listed model explicitly. If Ubuntu
cannot reach the Windows-hosted service at that origin, diagnose the known service
address/binding before changing `--endpoint`; do not interpret transport failure as
an incapable model. `OLLAMA_BASE_URL` and `OLLAMA_MODEL` can supply the same explicit
settings. URLs must be HTTP(S) origins without credentials, paths, queries or
fragments. Request timeouts, response-size caps, completed-generation checks and
model identity checks fail visibly. Raw HTTP bodies/errors are withheld on failure.

Expected strict probe result is `OLLAMA_STRICT_ACTION=PASS` and `LIVE_MODEL=PASS`.
It also prints `AGENT_REASONING=NOT_RUN`: reproducing one valid action does not prove
investigation quality. The probe saves a bounded failed receipt when generation
fails, if a new output path was supplied. Model token counts absent from a response
remain null, not zero.

The Ollama contract is `POST /api/chat`, `stream=false`, JSON Schema in `format`,
`temperature=0`, `num_predict=768` and context setting `8192`. Installed local model
support must actually be tested. No native provider tool execution is delegated;
model output is parsed as data in the same strict action envelope. The adapter is
based on the official [chat API](https://docs.ollama.com/api/chat) and
[structured-output documentation](https://docs.ollama.com/capabilities/structured-outputs).

## Run actual model inference with the live sources and memory bridge

After the model probe passes:

```bash
source ~/zetaris-setup/zetaris-platform/.venv-jdbc/bin/activate
python scripts/run_agent.py \
  --data-mode zetaris \
  --snapshot data/synthetic/fx_32e8b610 \
  --database AFYAEVIDENCE_REVISION \
  --jar "$HOME/zetaris-setup/zetaris-platform/jdbc/ndp-jdbc-driver-2.4.3.1-7eff043-driver.jar" \
  --model-provider ollama \
  --endpoint http://127.0.0.1:8082 \
  --model qwen2.5:3b \
  --memory hmem_reference \
  --bridge-dir bridges/hmem \
  --output runtime/agent-live-revision.json
```

The JDBC user defaults to `admin@zetaris.com`; the password is prompted privately
unless supplied through the existing local environment. Source collection verifies
all full-table hashes before analysis. It never replays CSV after a live failure.
The actual H-MEM bridge uses persistent scope directories under `runtime/memory`
and reviewed-note events in `runtime/review-notes.sqlite3`; these paths are host
configuration, not model arguments. The separate integration smoke used temporary
stores, so a first real agent run may honestly recall **zero** notes. It does not
invent, auto-approve or seed notes. Pending memory sync is disclosed; recall is not
an outbox write. Model-controlled writes and automatic memory dreaming are absent.

Memory is recalled once as a mandatory baseline against the bounded question,
before model dispatch. The host freezes a separate memory cutoff at CLI start;
`--memory-as-of` can explicitly set one. The reporting-data cutoff defaults to
`2026-01-15T00:00:00Z`, independently. Further memory queries remain scope- and
cutoff-bound. Historical notes keep original review/snapshot provenance and their
untrusted/non-measurement labels. They never become current metric references.

Successful execution prints `AGENT_EXECUTION=PASS`,
`EXECUTION_STATUS=ready_for_review`, `REVIEW_STATUS=awaiting_human_review`, and
separate actual model/source/memory statuses. A successful model call is not an
approved brief. A failed model or dependency run remains failed, preserves the
source facts when available and writes a trace receipt; no scripted success is
substituted. Setup errors also receive a failed receipt when possible.

## Actions, tools and budgets

`schemas/agent-action.schema.json` is the exported protocol. The matching runtime
schema is sent to Ollama; a regression test detects export drift. The standard-
library validator rejects unknown fields, duplicate JSON keys, non-JSON/fenced
responses, non-finite numbers, incorrect types and overlong lists/text. No new
third-party Python runtime dependency is introduced. Proposed HTTP/API schemas
remain separate work; see [ADR 0002](adr/0002-bounded-template-agent.md).

Allowed tools are the five names in [CONTRACTS.md](CONTRACTS.md): reporting quality,
canonical/raw indicators, matched facilities, scoped source records and historical
review recall. The host injects the fixed bundle/scope; model arguments cannot
select a database, snapshot, cutoff, district or output path. Quality and canonical
facts are mandatory before the first model call. At least one optional follow-up
must execute before a candidate brief is accepted.

Hard dispatch limits are four provider calls, ten tool invocations including
mandatory baselines, and one validation-repair opportunity within that same provider
budget. Completed tool+argument pairs are listed explicitly in the initial context.
A repeated pair is rejected before execution and may consume the single shared
validation repair; a second invalid action stops predictably. No duplicate tool
executes, no budget grows, and no failed run falls back to a scripted result.
The loop checks its
600-second deadline and cancellation before/after dispatch; per-model request
socket timeout is at most 180 seconds and bounded by remaining loop time. These
are not a tested hard end-to-end wall-clock guarantee: source collection precedes
the loop, HTTP socket timeouts do not guarantee cancellation of remote generation,
and the future supervised worker is still required to terminate stalled execution.
Ctrl+C produces a cancelled receipt where possible. No background automatic retry
is added for failed actual provider requests.

The receipt retains model actions, tool arguments/results, bounded provider replies,
usage where available, validation errors, the immutable scope/evidence bundle and
reference mappings. Provider errors do not expose credentials or raw transport
messages. Treat trace source/model text as untrusted if a future UI renders it.

## Numbers, explanations and references

Models see short **run-bound aliases** for host-owned metric/evidence IDs. Aliases
resolve to full original IDs in the receipt. A brief may reference only metrics and
evidence already shown in that run, and historical context actually recalled.
Fabricated IDs, cross-run aliases and future versions are rejected. Required
supporting metric sets are declared by category; unseen raw metrics require an
actual raw-diagnostic tool call before a reporting-artefact claim can be accepted.
Source evidence must cover each observable comparison period. If no reports have
arrived, registry evidence supports the explicit insufficient-data result.

A proposed brief contains only reviewed explanation/limitation/next-check codes and
references, not model-written numerical sentences or unrestricted clinical prose.
The host renders every numeric clause from the exact fact catalogue and attaches
full source input references. It validates the proposed category against available
facts: testing increase with unchanged positivity; revision-only artefact; mixed
artefact/residual; unresolved canonical change; insufficient comparative evidence;
or unchanged canonical positives. Those are bounded synthetic workflow rules, not
clinical alert thresholds or proof of epidemiological cause. Direction or evidence
outside these constructions remains unresolved.

Templates explicitly avoid diagnosis, treatment, outbreak declaration and causal
attribution. Human-review and synthetic-data limitations cannot be removed.
This intentionally constrained first agent supports useful follow-up selection
while preventing free-text arithmetic or authority changes. It does not demonstrate
open-ended causal reasoning. A valid candidate still sets
`semantic_review_required=true` and `approval=null`. The authenticated review route,
reviewer session/CSRF/idempotency and append-only decisions are a later slice.

## Actual validation and remaining gates

Local validation: **107 tests pass**, including strict parser/authority boundaries,
all core/edge scripted cases, earlier-cutoff visibility, unknown references,
unsupported categories, one repair, repeated calls, call/deadline/cancellation
budgets, provider failure, prompt-injection labels, actual H-MEM recall without
current-measurement contamination and saved successful/failed CLI receipts. Fake
HTTP tests check transport/schema/completion/usage/error handling; these are not
actual Ollama calls. The built wheel excludes evaluator data/answers and passes
isolated deterministic and scripted-agent execution outside the repository.

The operator has already reported actual Zetaris runtime and pinned H-MEM bridge
acceptance. Actual Ollama capability and the combined model-driven run remain
**NOT_RUN here** because the remote development environment cannot reach the
operator's local service. They must be established with the commands above.
The release design's repeated actual-model scenario evaluations, source-linked
semantic review, worker interruption/recovery, authenticated human-review UI and
end-to-end release gates remain pending. GitHub-hosted CI is still subject to the
known account budget/startup block; no hosted PASS is claimed.
