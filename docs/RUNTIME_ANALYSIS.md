# Runtime snapshots and deterministic analysis

This increment implements Issue 03's bounded data and calculation layer. It does
not run a model, expose an agent tool registry, approve findings or provide a web
interface. Runtime code is under `src/afyaevidence` and imports no evaluator code,
scenario recipes, answer keys or repository scripts.

## What is implemented

- `snapshot.py`: manifest validation, CSV byte/hash validation, fixed fixture caps,
  canonical reconciliation, detached immutable snapshots and exclusive snapshot
  archive creation. Source rows use tuples of immutable schema values; accessors
  return copies. Content IDs are independent of transport and input row order.
- `jdbc.py`: exact supplied Zetaris driver, validated identifiers/JAR/URL, separate
  SELECT calls, bounded complete reads, no dataset filter hiding stray rows, and
  closure on success/failure/interruption. The local manifest is required; live
  collection reads the database, not the fixture CSVs. It never falls back to CSV.
- `analysis.py`: frozen district/month/cutoff request, latest **observed** version
  selection, raw/canonical/matched comparisons, reporting coverage, exclusions,
  revisions and matched-facility contributions. Future versions do not enter
  visible evidence before their receipt cutoff. Invalid/withdrawn latest versions
  never restore an older version. Missing reports/counts differ from true zeros.
- A scoped evidence registry and metric catalogue: deterministic IDs, source table
  and record hashes, duplicate occurrence identity, exact rational values,
  calculation version, original count inputs, cohort, view and undefined reasons.
  Evidence/metric lookup rejects unknown IDs and IDs from another scope/cutoff.
- A fresh-process CLI and JSON receipts. Input collection and quality status are
  independent: successful computation may produce partial or insufficient evidence.
  Fixture/live/model/memory modes remain explicit.

The runtime calculation was ported from the bounded reference while retaining the
independent answer-key tests. The evaluator reference is still separate. Runtime
integrity checks focus on the requested two months. A known, unrelated period's
record does not poison these aggregates. Orphan logs cannot be assigned a known
period, so they conservatively block selected-scope aggregates. Unknown facilities
and contradictory identities block claims; duplicate report/version keys block the
affected report. Malformed schema values, registry conflicts and exceeded fixture
limits fail closed rather than produce totals. This is a bounded synthetic-data
implementation, not a general real-health-data validator.

## Run locally from the existing checkout

```bash
git pull --ff-only origin codex/architecture-and-jdbc-probe
python -m unittest discover -s tests -v
python scripts/analyse_snapshot.py \
  --mode fixture \
  --snapshot data/synthetic/fx_32e8b610 \
  --snapshot-output runtime/revision-fixture-snapshot.json \
  --output runtime/revision-fixture-analysis.json
```

Both output paths must be new. Existing files are never overwritten. Keep the
previous local Git stash saved. No new clone or dependency installation is needed
for fixture mode (Python 3.12+). The runtime is also runnable as
`python -m afyaevidence.cli` from an installed wheel, with the same flags.

The full-batch snapshot archive includes all 24 months, including future receipts
relative to the requested cutoff. It is a private operator/audit artifact and must
not be exposed to a model tool or mounted as prompt-accessible content. The
analysis receipt includes only scoped, observation-eligible evidence, plus
structural unpaired records needed to expose integrity failures. Whole-table hashes
necessarily cover the entire immutable source batch. Neither local archives nor
receipts are tamper-proof against local administrators. A partial file left by an
interrupted write is not a successful receipt; rerun using a new output path.

## Run the runtime layer against your Zetaris instance

The operator has already reported full snapshot JDBC reconciliation, all three
hashes, a 145-row join, and reference parity for `fx_32e8b610`. This new runtime
gateway is independently tested with fake transports here; run it on the operator's
machine to establish its own real execution receipt:

```bash
source ~/zetaris-setup/zetaris-platform/.venv-jdbc/bin/activate
export ZETARIS_USERNAME='admin@zetaris.com'
python scripts/analyse_snapshot.py \
  --mode zetaris \
  --snapshot data/synthetic/fx_32e8b610 \
  --database AFYAEVIDENCE_REVISION \
  --jar "$HOME/zetaris-setup/zetaris-platform/jdbc/ndp-jdbc-driver-2.4.3.1-7eff043-driver.jar" \
  --snapshot-output runtime/revision-zetaris-snapshot.json \
  --output runtime/revision-zetaris-analysis.json
```

The default user ID is `admin@zetaris.com`; an explicit local environment setting
can override it. Password input is hidden. Alternatively use a local
`ZETARIS_PASSWORD` environment setting. There is no password CLI flag. Do not
commit credentials, JARs, receipts or snapshots; `runtime/` is already gitignored.
The URL defaults to `jdbc:zetaris:lightning@localhost:10000`; override only through
`--url` or `ZETARIS_JDBC_URL`. No Spark session is started.

Expected final lines for the revision dataset at the default cutoff:

```text
TARGET_CANONICAL_TESTED=500
TARGET_CANONICAL_POSITIVE=100
TARGET_RAW_TESTED=600
TARGET_RAW_POSITIVE=120
ANALYSIS_STATUS=complete
DETERMINISTIC_ANALYSIS=PASS
LIVE_ZETARIS=PASS
LIVE_MODEL=NOT_RUN
LIVE_HMEM=NOT_RUN
```

Fixture mode prints `LIVE_ZETARIS=NOT_RUN`. A real failure exits non-zero, prints
FAIL and never reruns in fixture mode. The runtime gateway intentionally uses three
bounded source reads; the actual SQL join remains a separate verifier acceptance
check, not an unnecessary repeated runtime query. Fresh-process invocation avoids
forking/reloading an active JPype JVM. Driver query timeout/cancellation guarantees
remain unverified: use Ctrl+C for a stalled operator run; the supervised worker
process and job lifecycle are a subsequent implementation slice.

## Exact values, provenance and comparison populations

Metric `numerator` and `denominator` encode an exact reduced rational value. For
example mixed raw target positivity is `145/6` percent. `value` is an integer when
exact, otherwise a decimal string rounded to 12 fractional digits. `input_values`
retains the underlying count totals, such as 145 positive / 600 tested, or the
comparison/target inputs for changes. Calculations preserve integers/Fractions;
presentation rounding never feeds subsequent arithmetic. Percent changes and
percentage-point differences remain distinct.

`summary` contains legacy display values for inspection/reference parity. Trusted
numeric rendering should use the metric catalogue, not recalculate from those
floating-point display values. Undefined percentages are null with explicit
reasons (zero baseline, zero tested denominator or missing comparative evidence).

Metric evidence lists retain bounded scope inputs, including the registry and
excluded versions needed to reproduce selection and coverage. These are broader
than just the rows summed in a numerator. `quality` identifies missing and unmatched
facilities, revisions and latest-version exclusion reasons. Matched contributions
include only facilities valid in both periods. All-available partial comparisons
carry an incomplete-coverage reason and must not be treated as a like-for-like
district trend. Source-record IDs resolve only in their own analysis bundle.
The source snapshot ID identifies data content; the analysis ID additionally pins
scope, cutoff and calculation version. Live receipts record source namespace,
retrieval completion time and query-template version, never credentials.

## Checks and remaining work

Local validation: 67 tests passed, all 16 independent evaluator cases matched the
runtime summary, reproducible source bytes passed, and the built runtime wheel
passed both its member allowlist and isolated-process fixture execution without
the repository's evaluator package. Tests cover mutation, input order, provenance
resolution, future-version visibility, partial coverage, exact rational arithmetic,
zero denominators, live/fixture parity through fake transports, JDBC failure,
source overflow, schema/hash changes and exclusive receipt/archive creation.

CI includes deterministic runtime execution and isolated wheel smoke. GitHub
Actions has an account-level budget/startup restriction; no hosted PASS is claimed.
The previously reported real three-table verifier PASS is retained as operator
integration evidence. This runtime CLI's own real JDBC run remains NOT_RUN here.

The next slices are the supervised worker/storage lifecycle, actual Meterless
H-MEM integration, bounded model-driven tools and human-review interface. No model,
memory, clinical validity, causal explanation, review authority or deployment
completion is claimed by this data/analysis layer.

## Subsequent operator runtime receipt

The operator reported `DATA_MODE=zetaris`, snapshot ID
`ss_64122fa0ad6e9740549aef0a6fce7c29dd7845498914b9e43da96c04a6d86852`,
`ANALYSIS_STATUS=complete`, `DETERMINISTIC_ANALYSIS=PASS` and `LIVE_ZETARIS=PASS`.
Expected comparison/canonical/raw counts matched and the analysis receipt was
saved to `runtime/revision-zetaris-analysis.json` on their machine. This establishes
the runtime path for that revision snapshot. Actual local H-MEM bridge verification
is described in [HMEM_BRIDGE.md](HMEM_BRIDGE.md); model and review UI are separate.
