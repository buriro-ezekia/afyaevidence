# CPU workflow verification — 22 October 2026

**Actual Ollama inference with fixture data: PASS. Combined Zetaris/Ollama/H-MEM:
BLOCKED at JDBC login.** No combined completion, deployment or human approval is
claimed. Full receipts and earlier failed attempts remain in the gitignored local
`runtime/` directory; this document contains only sanitised results.

## Scheduling and context

The reported investigator-3 requests spent 134.14, 138.41 and 201.18 seconds on
exploration; its fourth request exhausted the 600-second deadline. Reserving a call
did not reserve time. `--execution-profile cpu` now collects quality, canonical and
raw comparisons plus configured scoped memory before dispatch. The actual model
chooses one finite follow-up, then a second brief-only request selects explanation,
references and optional review codes. Its first request reserves a final inference
allowance. No third exploration request or automatic repair is permitted.

Fresh phase contexts remove conversation history, duplicate schema text and
redundant provenance catalogues. All scoped source-index rows, canonical facts,
quality exclusions and historical notes remain; raw positive totals contain the
allowed categories' raw prerequisites. Full records and metric inputs remain in
the receipt. Mandatory review codes and finite period-covering citations are
generation constraints as well as independent host checks. The standard profile
retains its four-call/one-repair policy.

The exact mocked HTTP payload comparison below uses the same revision fixture,
`qwen2.5:3b` identifier, disabled memory and scripted raw/matched/brief versus CPU
matched/brief actions. These are byte measurements, **not model inference or token
estimates**:

| Profile | Request bytes | Total |
|---|---|---:|
| investigator-3 | 15,638 / 19,984 / 22,392 | 58,014 |
| CPU investigator-4 | 9,824 / 14,200 | 24,024 |

The CPU sequence is 58.6% smaller overall; its first/final requests are 37.2%/36.6%
smaller. Actual sizes vary with the model's chosen follow-up and memory contents.

## Actual inference

Ubuntu reached the explicitly configured Windows Ollama endpoint
`http://172.22.160.1:11434`; it listed the installed `qwen2.5:1.5b`. This address was
verified for this session and must be rechecked after a WSL restart.

| Local receipt | Result | Request seconds |
|---|---|---|
| `runtime/cpu-fixture-live-20261022-01.json` | FAIL: missing mandatory synthetic-data limitation | 50.76 / 117.82 |
| `runtime/cpu-fixture-live-20261022-02.json` | FAIL: repeated evidence IDs (`invalid_list`) | 63.98 / 138.57 |
| `runtime/cpu-fixture-live-20261022-03.json` | PASS: valid review-only candidate | 90.50 / 110.78 |

The first two failures drove stricter generation constraints; neither was repaired
into success by the host. The third run used `model_mode=ollama`, `data_mode=fixture`
and `memory_mode=disabled_fixture`. It selected a scoped source-record follow-up
and `reporting_artefact_supported`, completed two calls with zero repairs and
produced `review_status=awaiting_human_review`, `semantic_review_required=true`,
`approval=null`. Total provider time was 201.28 seconds within the 600-second loop
deadline. This is one successful actual-model case, not a repeated semantic
evaluation across all scenarios.

Ollama supplied 2,318 / 3,335 prompt tokens and 229 / 165 generated tokens. Actual
request sizes were 9,826 / 14,455 bytes; both had two messages. Full supplied usage,
nanosecond timings, actual timeouts, phases, menus, responses and references are in
the receipt. Missing provider metadata is never replaced by zero or a byte-derived
token estimate.

Fixture: `fx_32e8b610`, district D001, October versus November 2025, reporting cutoff
`2026-01-15T00:00:00Z`. Snapshot:
`ss_64122fa0ad6e9740549aef0a6fce7c29dd7845498914b9e43da96c04a6d86852`.

Receipt SHA-256 values:

- Attempt 01: `0464b569c3b4aabc10c6dc4a97b2367bb46d2b0ebb8c29b70545ff93449b7244`
- Attempt 02: `060f8267c2a2000ea288d863d806a16e9a5efa168c7314a7f10afadff3504504`
- Successful attempt 03: `6eab63bd33d2ba452bdfb18bb750c40d2485a4ac2a4961f0bedeed9120e285e6`

## Combined live gate

The configured `localhost:10000` endpoint accepted TCP connections. The supplied
Zetaris driver returned `Error validating the login` for `admin@zetaris.com`, both
with existing local setup configuration and the operator-supplied credential. Raw
driver errors and credentials are withheld from application receipts. The final
diagnostic confirmed the login failure after explicit credential redaction; it
does not establish successful JDBC access.

`runtime/cpu-combined-live-20261022-01.json` through `-06.json` preserve the failed
attempts. The later receipts identify `failure_stage=source_collection`; no model
dispatch or H-MEM recall occurred. The final receipt SHA-256 is
`bb9be08aeb701368183ccbe11f50de9ffd63b3af403efb13f541f4a15c4530d9`.

The runtime still uses only `com.zetaris.lightning.jdbc.LightningDriver`,
`jdbc:zetaris:lightning@localhost:10000`, the existing
`AFYAEVIDENCE_REVISION` tables and one SELECT statement per call. No driver,
source record, source registration or Spark setup was changed. Supplied JAR SHA-256:
`a344921760cb7e3747535ae77a25aef095150f4298632089096bca680ce13f6c`.

Remaining acceptance: verify the working account/password locally, then run the
[complete CPU command](AGENT_LOOP.md#run-actual-model-inference-with-the-live-sources-and-memory-bridge).
Keep the password in the private prompt or local environment. Require a new receipt
with actual Zetaris, Ollama and H-MEM modes and a valid review-only candidate before
marking this gate verified. Earlier operator-reported source successes remain
historical evidence and do not turn this failed check into PASS.

## Regression, memory and package checks

Ubuntu Python 3.12.3 and Node 24.22.1 ran **150 tests: PASS** (51.787 seconds).
Coverage includes simulated observed latency, exact two-phase dispatch, reserved
capacity, late responses, cancellation during rendering, duplicate/unseen references,
category/supporting-metric/period validation, provider failure, scoped memory,
outbox/restart behaviour and failed-receipt retention. Test providers and fake HTTP
remain explicitly distinguished from the actual inference above.

An earlier 144-test run during inference exceeded the existing five-second wait in
one cross-process lock test. Its failed log is preserved as
`runtime/cpu-unit-check-20261022.log`. Separate 149-test and final 150-test runs passed
without changing the lock or relaxing that test. Final log:
`runtime/cpu-final-unit-check-20261022-02.log`.

Actual pinned H-MEM smoke: **PASS** for persistence, provenance, scope isolation,
chronology and outbox retry. Receipt `runtime/cpu-hmem-check-20261022.json`, SHA-256
`02e04ae1742d4d14e2c3c2498671dd93328ef430800f8c95a5b269f74344dd36`.
This used temporary stores and fixture provenance, not the blocked combined run.
The upstream reference still uses mock hash embeddings and prototype JSON storage.

Deterministic probe and all 15 synthetic snapshots reproduced; all 16 independent
evaluator cases and three-table fixture preflight passed. Both scripted profiles
passed all 16 cases, for **32 labelled scripted executions**. The final wheel built
with isolated pinned `setuptools==84.0.0` passed its allowlist and both profile
smokes outside the repository. Evaluator code/answers, source data, credentials,
driver JARs and runtime receipts are excluded. Final wheel SHA-256:
`e240d99b7df59ef645ba6ac83d7f54ae216c302f4d59120dc03fc31d23538388`.

Scheduler/provider source SHA-256 values used by the successful actual fixture run:

- `agent.py`: `073f1e4ad254f83717c86752cf5d9b74a2640122f4f69c90dbdf7a9b9bbbfb50`
- `model.py`: `cb50aafff2e6109ea440ba395a788f6ac2a25fd605c4babf58d1d6ad182e1212`

No hosted CI, authenticated human-review API/UI, supervised worker, deployment or
clinical approval PASS is claimed by these checks.
