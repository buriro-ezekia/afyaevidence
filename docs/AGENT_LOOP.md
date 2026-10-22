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

The operator verified Ollama in Windows and reached it from Ubuntu at
`http://172.22.160.1:11434`, bound specifically to the Windows WSL interface.
Both `qwen2.5:3b` and `qwen2.5:1.5b` passed the single-action probe. The 3b
combined run exceeded its 180-second request timeout; the 1.5b run returned
a repeated mandatory canonical comparison. The endpoint is host-specific and
can change after a WSL restart; use the actual verified interface address. The adapter never starts a
server, downloads a model, scans ports, follows HTTP redirects, uses environment
proxies or silently changes providers. Explicit host configuration is required.

```bash
python scripts/verify_model.py \
  --endpoint http://172.22.160.1:11434 \
  --list-models
```

Then check strict action generation with an actual installed model:

```bash
python scripts/verify_model.py \
  --endpoint http://172.22.160.1:11434 \
  --model qwen2.5:1.5b \
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

After the model probe passes, test actual inference with fixture data first:

```bash
python scripts/run_agent.py \
  --data-mode fixture --snapshot data/synthetic/fx_32e8b610 \
  --model-provider ollama --execution-profile cpu \
  --endpoint http://172.22.160.1:11434 --model qwen2.5:1.5b \
  --model-timeout 300 \
  --output "runtime/cpu-fixture-$(date -u +%Y%m%dT%H%M%SZ).json"
```

Use the currently verified endpoint; this address may change after restarting WSL.
This checks actual inference with fixture source access and disabled memory. Then
run the combined workflow in your existing Ubuntu checkout:

```bash
source ~/zetaris-setup/zetaris-platform/.venv-jdbc/bin/activate
source "$HOME/.nvm/nvm.sh"
nvm use 24
python scripts/run_agent.py \
  --data-mode zetaris \
  --snapshot data/synthetic/fx_32e8b610 \
  --database AFYAEVIDENCE_REVISION \
  --jar "$HOME/zetaris-setup/zetaris-platform/jdbc/ndp-jdbc-driver-2.4.3.1-7eff043-driver.jar" \
  --url jdbc:zetaris:lightning@localhost:10000 \
  --model-provider ollama \
  --execution-profile cpu \
  --endpoint http://172.22.160.1:11434 \
  --model qwen2.5:1.5b \
  --model-timeout 300 \
  --memory hmem_reference \
  --bridge-dir bridges/hmem \
  --output "runtime/agent-live-cpu-$(date -u +%Y%m%dT%H%M%SZ).json"
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
`2026-01-15T00:00:00Z`, independently. The finite follow-up menu does not expose additional memory queries; the
initial host-owned query stays scope- and cutoff-bound. Historical notes keep original review/snapshot provenance and their
untrusted/non-measurement labels. They never become current metric references.

Successful execution prints `AGENT_EXECUTION=PASS`,
`EXECUTION_STATUS=ready_for_review`, `REVIEW_STATUS=awaiting_human_review`, and
separate actual model/source/memory statuses. A successful model call is not an
approved brief. A failed model or dependency run remains failed, preserves the
source facts when available and writes a trace receipt; no scripted success is
substituted. Setup errors also receive a failed receipt when possible.

## Actions, tools and budgets

`schemas/agent-action.schema.json` is the exported superset protocol. Each
Ollama request receives a narrower, host-generated schema once in its `format`
field, with matching phase instructions and a compact action menu in the prompt.
The global superset is never advertised to the model
in an investigation. Schema-export consistency and fake-HTTP integration tests
verify the two contracts. The standard-
library validator rejects unknown fields, duplicate JSON keys, non-JSON/fenced
responses, non-finite numbers, incorrect types and overlong lists/text. No new
third-party Python runtime dependency is introduced. Proposed HTTP/API schemas
remain separate work; see [ADR 0002](adr/0002-bounded-template-agent.md).

Allowed tools are the five names in [CONTRACTS.md](CONTRACTS.md): reporting quality,
canonical/raw indicators, matched facilities, scoped source records and historical
review recall. The host injects the fixed bundle/scope; model arguments cannot
select a database, snapshot, cutoff, district or output path. Quality and canonical
facts are mandatory before the first model call. At least one model-selected follow-up
must execute before a candidate brief is accepted.

Prompt version `investigator-4` supports two explicit scheduling profiles.
`--execution-profile standard` preserves the four-request policy and 180-second
default timeout. It supplies finite exact follow-up actions: raw
version comparison, matched facilities with or without contributions, and stable
source batches of at most 20 scoped evidence records grouped by table/month.
A completed pair is removed, and either matched variant completes that analysis.
Quality, canonical comparison and initial memory recall are already complete and
never appear as model choices. The host validates exact menu membership before
dispatch even if a provider ignores the schema. The original duplicate guard
still rejects known pairs before any dependency executes.

If the model first inspects matched facilities or source records, the next
choice is raw comparison so the model sees version effects before proposing an
explanation. Brief generation requires at least one follow-up plus raw facts.
After these prerequisites, the last available call is brief-only. The model
still chooses a category and references; the host does not fill in an answer
when inference fails. Brief schemas enumerate only shown metric/evidence aliases
and recalled contexts. Category prerequisites, supporting metrics, period coverage
and human-review limitations are validated separately after generation.

For the standard profile, hard dispatch limits are four provider calls, ten tool invocations including
mandatory baselines, and one validation-repair opportunity within that same provider
budget. Completed tool+argument pairs are listed explicitly in the initial context.
A repeated pair is rejected before execution and may consume the single shared
validation repair; a second invalid action stops predictably. No duplicate tool
executes, no budget grows, and no failed run falls back to a scripted result.
`--execution-profile cpu` changes scheduling, not evidence or approval rules:

1. The host collects reporting quality, canonical comparison, raw-version
   comparison and configured scoped H-MEM context before dispatch.
2. The first model request chooses one matched-facility comparison with
   contributions or one finite scoped source-record batch. Raw, quality, canonical
   and memory operations are already complete and absent from the menu.
3. The second request accepts only a candidate brief. The model still chooses the
   explanation category, metric/evidence references, limitations and next checks.

CPU mode permits at most two requests, including invalid responses. It does not
spend a third call repairing or exploring. A first-turn validation failure stops
without consuming the reserved brief call. A second-turn failure preserves a failed
receipt. There is no host-generated replacement answer. Ten tool calls remain the
outer cap; normal CPU runs use four, or five with H-MEM.

CPU mode defaults to a 300-second per-request cap and reserves
`min(request_timeout, overall_deadline / 2)` seconds for the brief. Before the first
dispatch its timeout is also capped at remaining time minus that reserve. If no
positive allowance remains, dispatch fails with `brief_capacity_unavailable`.
Before the final dispatch the request cap is clamped to the actual remaining time.
A caller-supplied model-call budget below two cannot spend its sole call exploring.
The default overall deadline remains 600 seconds.

Each CPU request has fresh phase-specific context, without conversation history,
completed-action catalogues or a second copy of the schema. The initial phase
omits unused brief requirements. Both phases retain every scoped source-index row,
all canonical facts, quality exclusions, missingness and historical notes. Raw
positive totals supply all raw prerequisites for the allowed explanation codes.
The final phase includes the chosen follow-up result and brief requirements.
Fact cohort/view labels occur once per group. Repeated provenance IDs in revision
lists and redundant report identifiers resolve through the source index and full
host registry. This projection is explicitly declared in the prompt: full records
and raw testing/positivity facts remain in the receipt. The schema and validator
allow only references actually visible in that phase. Mandatory review codes are
constrained in the final schema as well as checked by the host; optional codes
remain model choices.

CPU brief citations are a finite choice of one source-index reference per observed
month, in chronological order (one registry reference if no reports are visible).
Every combination is available to the model; no scenario answer is selected by the
host. This enforces distinct, period-covering citations even when the provider's
grammar ignores `uniqueItems`. The host still checks reference visibility, category
prerequisites, required supporting metrics and period coverage independently. These
are concise citations: all input evidence for each numerical statement remains in
the rendered candidate and full registry.

The loop checks its deadline and cancellation before and after dispatch, and before
accepting the rendered candidate. Timeout, deadline, cancellation, provider failure
and evidence validation have distinct failure codes. A response arriving after its
request allowance is rejected even before the overall deadline. The receipt records
the configured limits and each dispatched request timeout. A late response cannot
be accepted after the loop deadline. These
are not a tested hard end-to-end wall-clock guarantee: source collection precedes
the loop, HTTP socket timeouts do not guarantee cancellation of remote generation,
and the future supervised worker is still required to terminate stalled execution.
Ctrl+C produces a cancelled receipt where possible. No background automatic retry
is added for failed actual provider requests.

The receipt retains execution profile, per-turn available actions/phase, actual
timeout, remaining/reserved time, host elapsed time, model actions, tool arguments/results, bounded provider replies,
usage where available, validation errors, the immutable scope/evidence bundle and
reference mappings. Exact request/message/schema byte sizes are separate from token
counts. Provider token counts and nanosecond timings remain null when absent;
failed requests retain size/timing diagnostics too. Provider errors do not expose credentials or raw transport
messages. Timeout, HTTP failure, transport failure, oversized context and invalid
response have separate sanitised codes. The CLI prints prompt version, call counts
and failure-stage summaries so the operator can diagnose a failed run directly. Treat trace source/model text as untrusted if a future UI renders it.

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

The [CPU verification record](CPU_VERIFICATION.md) separates actual inference,
actual H-MEM, deterministic tests, fake HTTP and the combined live gate.
`qwen2.5:1.5b` generated a valid fixture-backed candidate in two requests, taking
90.50 and 110.78 seconds. Two earlier actual runs were rejected for missing review
limitations and repeated evidence IDs; their failed receipts remain preserved.

The combined run reached the configured Zetaris endpoint but failed with the
sanitised driver message `Error validating the login`, including with the
operator-supplied credential. No model dispatch or memory recall occurred in those
combined attempts. This is **BLOCKED**, not PASS; a new combined receipt with
`data_mode=zetaris`, `model_mode=ollama`, `memory_mode=hmem_reference` and a valid
review-only candidate is still required.

The full regression suite, independent synthetic evaluator, both scripted profiles,
actual pinned H-MEM lifecycle checks and isolated wheel checks have separate
results in the verification record. An initial cross-process lock test exceeded
its five-second child-process wait during concurrent inference; the final separate
run passed without relaxing that test. No hosted CI PASS is claimed.

One valid synthetic fixture run does not establish repeated actual-model scenario
performance or semantic/clinical approval. The authenticated review API/UI,
supervised worker interruption/recovery, full release evaluation and deployment
remain pending.
