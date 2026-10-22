# AfyaEvidence data contract

Status: the synthetic suite, strict source normalisation and evaluator reference implement the fixture subset described in [SYNTHETIC_DATA.md](SYNTHETIC_DATA.md). The [runtime snapshot/analysis layer](RUNTIME_ANALYSIS.md) is implemented with local tests. The operator reported the original probe and full three-table verifier PASS; the new runtime CLI's real execution receipt remains pending. Model tools, worker and review services remain planned.

## Dataset and scope

- One fictional district, `D001`, and six fictional facilities, `F001`–`F006`.
- Calendar months `2024-01-01` through `2025-12-01`: 144 expected facility-months.
- A dataset is an immutable snapshot of three CSV files. Revisions add raw rows;
  they do not increase the number of expected facility-months.
- CSVs contain opaque `dataset_id` values, never scenario names or expected answers.
- A separate manifest records dataset ID, schema version, generator version, fixed
  seed, fixed generation timestamp, row counts and two distinct SHA-256 digests per
  table: exact CSV byte hash for provenance, and canonical row-content hash for JDBC
  result reconciliation. These hashes are not interchangeable.
- UTF-8 CSV with headers; ISO dates; UTC timestamps with `Z`; non-negative decimal
  integers for counts. Empty count cells mean missing, not zero. No personal data.

## Three source tables

| Table / grain | Required fields | Keys and constraints |
|---|---|---|
| `malaria_monthly`: one report version | `dataset_id`, `report_id`, `report_version`, `facility_id`, `period_month`, `suspected_episodes`, `tested_episodes`, `positive_episodes` | Primary key `(dataset_id, report_id, report_version)`; positive integer version; month is its first calendar day. |
| `reporting_log`: one event per report version | `dataset_id`, `report_id`, `report_version`, `received_at_utc`, `status`, `declared_complete` | Same primary key; exactly one event joins each report version; status is `accepted` or `withdrawn`; Boolean is `true` or `false`. |
| `facility_registry`: one facility | `dataset_id`, `facility_id`, `district_id`, `facility_type`, `active_from`, `active_to` | Primary key `(dataset_id, facility_id)`; `active_to` is exclusive and empty means no end. All six are active throughout the baseline. |

`report_id` is stable for a facility-month. Multiple report IDs for that same
facility-month are a conflict. Every version retains the same facility and period.
Each report-version row must have a registry match and exactly one log match.
Log rows without report rows are also findings; inner joins must not hide them.

The synthetic measure is a suspected episode with at most one diagnostic
determination: positive episodes are a subset of tested episodes, and tested
episodes are a subset of suspected episodes. Hence `0 <= positive <= tested <=
suspected`. This intentionally restricted definition must not be assumed for real
datasets containing repeat tests or different reporting populations.

## Investigation request and as-of selection

The trusted request fixes `district_id`, `comparison_month`, `target_month`,
`as_of_utc` and dataset snapshot. The service supplies `dataset_id`; the model
cannot switch snapshots, months or districts while an investigation is running.

1. Retrieve the bounded immutable source batch through Zetaris and reconcile its
   canonical table digests. Determine observation-eligible report/log pairs before
   calculating analytical findings. Structural unpaired/conflicting records produce
   an explicit affected-scope integrity result, not a silent join omission.
2. Retain log events with `received_at_utc <= as_of_utc`. Later arrivals remain
   invisible to that investigation, even when the snapshot contains them.
3. For each report ID, choose the highest version observed by the cutoff. Version
   order governs corrections; an older version arriving later does not supersede it.
4. Exclude a latest version marked `withdrawn`. An invalid latest version makes
   that facility-month unavailable. Neither condition silently falls back to an
   earlier version; show its evidence, exclusion reason and coverage consequence.
5. Produce one canonical record per facility-month, or an explicit conflict/missing
   finding. Raw all-version diagnostic totals sum only eligible versions received
   by the same cutoff, before canonical selection; never include future arrivals.
   Later records may enter whole-batch hashes but never visible earlier-run evidence.

The first implementation canonicalises and computes in deterministic Python after
Zetaris retrieval. SQL aggregation is a later optimisation requiring parity checks.
Fixture validity limits: one dataset, six facilities, 24 months, at most three
report versions per facility-month and 432 rows in each report/log table. The
gateway's independent defensive retrieval cap is 2,000 rows per source; a batch
exceeding either its declared fixture limits or the retrieval cap fails explicitly.
It never truncates data and returns a successful total.

## Metrics and comparison rules

- `positive_total` and `tested_total` use canonical accepted records only.
- `positivity_pct = 100 * sum(positive_episodes) / sum(tested_episodes)` for aligned,
  available counts. Never average facility percentages to obtain district positivity.
- If tested total is zero, positivity is unavailable with `ZERO_DENOMINATOR`.
- Percentage change is `100 * (target - comparison) / comparison`; when comparison
  is zero, report the absolute change and undefined percentage, not infinity.
- Positivity differences use percentage points; keep underlying integers and
  round presentation only. These measures are not population incidence.
- Expected reports derive from the active registry, not the number of rows found.
  For future changing registries, a facility is expected if active at month start;
  partial-month coverage must be separately displayed.
- Receipt coverage is facility-months with any report received by cutoff / expected
  facilities, even if withdrawn or analytically invalid. Show accepted-report
  coverage separately using latest accepted report states. Analytical completeness
  additionally requires available required counts and passing checks;
  `declared_complete` alone never establishes analytical completeness.
- Show all-available totals, the common valid facility set and matched-facility
  totals. Explicitly disclose exclusions; missing reports never become zero counts.
- Lateness requires an explicit synthetic due-date configuration; do not infer an
  official reporting deadline or clinical threshold from these fixtures.

## Integrity outcomes

Duplicate primary keys, contradictory versions, unknown facilities, orphan logs,
invalid dates, negative counts and impossible count relationships produce findings.
The response distinguishes `usable`, `partial` and `unavailable` evidence. A fatal
integrity conflict prevents the affected aggregate claim; it does not erase the
records. Withdrawal and missing reporting are visible even if no counts are usable.

## Canonical table digest v1

Normalise JDBC and CSV values through the same declared schema: counts/versions as
integers, missing optional values as JSON null, Booleans as JSON true/false, dates
as `YYYY-MM-DD`, timestamps as UTC `YYYY-MM-DDTHH:MM:SSZ`, identifiers as exact
strings with no trimming or case folding. Restrict fixture timestamps to whole
seconds. Reject ambiguous/coercion-failing values instead of guessing.

For each table use its schema field order to encode each row as a compact JSON
array (UTF-8, no ASCII escaping, no optional spaces). Sort encoded row arrays by
their UTF-8 byte representation, retaining duplicate rows, then join them with one
LF after every row. Hash these bytes with SHA-256. Record algorithm
`afya-canonical-rows-v1` and field order in the manifest. Row order changes the
CSV byte hash but not this digest. Hash the full published table batch before
applying the investigation cutoff; do not compare filtered rows to a full-table
digest. The initial small fixtures permit bounded retrieval of the whole batch.

## Evidence and output contract

Each tool response includes snapshot hashes, cutoff, scope, calculation/template
version, input report-version IDs, exclusions, findings and deterministic metrics.
Evidence IDs are server-issued opaque references resolving to the scoped source
records. Metric IDs identify a value, unit, denominator and comparison population.

The model selects `metric_ref` IDs and `evidence_ids`; the server renders numeric
sentences from the metric catalogue rather than trusting model-written arithmetic.
Every ID must resolve inside this investigation. Unsupported causal language still
requires semantic evaluation and human review; valid citations alone do not prove it.

Human decisions are appended to a separate application review store. They never
overwrite source CSVs, canonical reports or the original generated brief. Dataset
manifests and runtime evidence are separate from evaluation-only answer keys.

## Dataset loading acceptance gate

Before claiming sponsor integration, retrieve all three tables through the specified
Zetaris JDBC driver and compare row counts, report IDs, canonical selections and
metrics against the Python reference for the same hashes/cutoff. A local CSV replay
is a fixture test, not proof that Zetaris has queried the source. Data registration
SQL and the ingestion route remain instance-verified implementation work.
