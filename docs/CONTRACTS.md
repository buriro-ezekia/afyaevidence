# Tool, API and persistence contracts

Status: proposed version 1 interfaces. Implement strict Pydantic schemas with unknown fields forbidden and export JSON Schemas during implementation. The examples below specify behaviour; they are not executed API calls.

## Request and modes

`POST /api/investigations` receives a district, two distinct months, an observation cutoff and an optional bounded question. The server resolves an opaque registered dataset to an immutable snapshot and injects it into the run. A maximum question length of 1,000 characters is sufficient; free text never expands data access.

```json
{
  "district_id": "D001",
  "comparison_month": "2025-10-01",
  "target_month": "2025-11-01",
  "as_of_utc": "2025-12-15T00:00:00Z",
  "question": "Investigate the change in confirmed episodes."
}
```

Require an `Idempotency-Key` header. A repeated key and identical request returns the same run; the same key with different content returns `409`. Timestamps are timezone-aware UTC; months are first-of-month dates. Reject unsupported district/month/cutoff values before queueing.

Run metadata includes three independent execution modes: `data_mode` (`fixture` or `zetaris`), `model_mode` (`scripted`, `ollama` or `meterless_runtime`) and `memory_mode` (`disabled_fixture` or `hmem_reference`). An integration result is not inferred from these labels; store actual dependency receipts. `zetaris` never falls back to CSV and a real provider failure never returns a scripted PASS.

## Model action protocol

Each step returns exactly one strict JSON action. Native provider tool calls may be mapped into this schema after capability tests. Text outside a permitted JSON envelope is invalid.

```json
{
  "type": "tool_call",
  "tool": "compare_matched_facilities",
  "arguments": {"include_contributions": true}
}
```

The application adds run/snapshot/scope to every invocation; the model cannot supply them. The alternative action is `propose_brief` with the candidate fields described below. Every response, retry and tool call consumes the configured global budget.

## Model-visible tools

| Tool | Model arguments | Returns |
|---|---|---|
| `get_reporting_quality` | None | Receipt/usable coverage, revisions, conflicts, missingness, exclusions and evidence IDs for the frozen two-month scope |
| `compare_monthly_indicators` | `view`: `canonical` or `raw_diagnostic` | Totals, changes and positivity with metric references; raw diagnostic results prominently identify invalid all-version aggregation |
| `compare_matched_facilities` | `include_contributions`: Boolean | Common valid cohort, unmatched facilities, paired indicators and contribution facts |
| `get_evidence_records` | At most 20 known `evidence_ids` | Scoped source record versions, provenance, exclusions and calculated-fact input links |
| `recall_review_context` | Bounded query string | At most three prior scoped approved notes with source, prior snapshot/run and staleness labels; never current health metrics |

Mandatory baseline quality and canonical indicator facts are collected before the optional loop, even if the model fails to request them. All follow-up data tools operate on the same immutable Zetaris-backed snapshot in live mode. No tool accepts SQL, filesystem paths, URLs, secrets, new source names or reviewer decisions.

## Evidence and metrics

Each result is an `EvidenceBundle` with `run_id`, `snapshot_id`, source hashes, `schema_version`, `cutoff`, district/month scope, query-template version, retrieval timestamps, record refs, metric refs, quality findings, exclusions and completeness status. Distinguish observations (`source_record`), derived metrics (`calculated_fact`) and remembered prior context (`review_context`). Only current observations/calculated facts can support current numerical claims.

Persist source records without modifying them. A source reference identifies table + dataset + key + report version + content hash. Resolve evidence only through the run registry; a plausible-looking ID is not sufficient. A derived metric links to the exact input record set and calculation definition. Retain full bounded input sets in storage, even if the prompt sees a summary.

A `MetricFact` contains:

| Field | Meaning |
|---|---|
| `metric_ref` | Opaque server-issued ID |
| `name` | Reviewed metric definition key |
| `value` | Exact integer or decimal string, or null |
| `unit` | `episodes`, `percent`, `percentage_points` or `facilities` |
| `numerator`, `denominator` | Underlying exact values when applicable |
| `period`, `cohort`, `view` | Two-month comparison and population definition |
| `evidence_ids` | Source records needed to reproduce it |
| `availability`, `reason` | Available/partial/unavailable with explicit reason |
| `calculation_version` | Versioned metric implementation |

A source retrieval succeeds only when the configured batch matches its manifest, all bounded rows are present and values normalise to the declared schema. Domain-quality failures are separate from connectivity; both remain visible.

## Candidate brief and semantic boundary

The model proposes `summary`, `possible_explanations`, `limitations`, `next_checks`, and typed claims. Every explanation includes supporting and counter-evidence references. Claims select server-owned `metric_refs`; the renderer inserts the numeric statement. If an explanation lacks discriminating evidence, label it possible or inconclusive instead of assigning an unsupported confidence percentage.

Example claim shape:

```json
{
  "claim_type": "observed_change",
  "metric_refs": ["m_positive_change", "m_positivity_difference"],
  "evidence_ids": ["ev_comparison_records", "ev_target_records"],
  "interpretation": "The available reporting checks do not establish the reason for the increase."
}
```

These illustrative IDs must be replaced by actual registry IDs. Validate every link, scope, unit, completeness status and permitted claim type. Reject unsupported free-text numbers and do not accept model-written calculations as metric facts. A schema/citation validator cannot establish causal truth: semantic evaluations and human review test explanations separately.

Execution outcome, analytical conclusion and human review are independent. A completed investigation may be `insufficient_data`; a reviewer can reject a validly generated candidate. Do not conflate either state with a technical failure.

## HTTP surface

| Method and route | Purpose | Authority |
|---|---|---|
| `GET /health/live` | Process health only | Local session |
| `GET /api/status` | Separate Zetaris/model/H-MEM readiness and mode | Local session; no secrets |
| `POST /api/investigations` | Validate and queue a bounded run; return `202` plus run ID | Browser session + Origin/CSRF |
| `GET /api/investigations/{id}` | Status, scope, candidate and mode labels | Same local scope |
| `GET /api/investigations/{id}/events?after=sequence` | Incremental progress polling | Same local scope |
| `GET /api/investigations/{id}/evidence/{evidence_id}` | Inspect current source/fact references | Exact run binding |
| `POST /api/investigations/{id}/cancel` | Stop dispatch and terminate child safely | Browser session + Origin/CSRF |
| `POST /api/investigations/{id}/reviews` | Append explicit reviewer disposition | Human route only; never agent tool |
| `GET /api/investigations/{id}/export?format=json` | Selected synthetic run export; `md` also supported | Same local scope |

Unknown/malformed input returns `422`, stale/idempotency conflicts `409`, forbidden local capability `403`, absent IDs `404`, queue saturation `429`, and unavailable dependencies `503` when no run can start. Dependency failure during a queued run persists a typed run error rather than pretending to be an HTTP success with a completed brief.

## Human review

A review request has `decision` (`accepted_for_follow_up`, `request_more_evidence` or `rejected`), a non-empty reason (maximum 2,000 characters) and `expected_revision`, plus an idempotency header. `accepted_for_follow_up` means the brief is useful for review; it is not clinical confirmation. Actor identity comes from the operator session, never the model or request body.

Append the decision, increment review revision and create any requested memory-outbox event in one SQLite transaction. Preserve the original candidate and source snapshot. A subsequent correction is another event. API capability checks apply even if a model imitates a review JSON object.

## Application storage

Proposed SQLite tables: `schema_migrations`, `investigations`, `run_events`, `source_snapshots`, `evidence_records`, `metric_facts`, `tool_calls`, `candidate_briefs`, `review_events`, `memory_outbox` and `memory_receipts`. Use foreign keys, unique run/event sequence numbers and idempotency identities. Store structured JSON with explicit schema versions; keep relational keys for run and scope checks. Use optimistic review revisions and a single atomic worker claim.

Runtime state and H-MEM stores live under a configured local application-state directory outside committed source. Source snapshots are immutable per run. Audit events are append-only by application convention; local database owners can alter them, so no tamper-proof guarantee is implied.
