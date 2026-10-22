# Reproducible synthetic-data suite

This increment implements the data foundation, not the investigation agent. All
facilities and observations are fictional. Counts represent episodes with at most
one diagnostic determination, as specified in [DATA_CONTRACT.md](DATA_CONTRACT.md).
They are neither incidence estimates nor clinical alert thresholds.

## Run from your existing checkout

In the Ubuntu terminal already open in the AfyaEvidence repository, update the
feature branch without discarding local changes:

```bash
git fetch origin
git switch codex/architecture-and-jdbc-probe
git pull --ff-only origin codex/architecture-and-jdbc-probe
python scripts/generate_synthetic.py --check
python scripts/evaluate_synthetic.py
python -m unittest discover -s tests -v
```

Use Python 3.12 or later; the existing JDBC environment is suitable. These commands
need no new dependencies, credentials, Java or running services. If Git reports
local changes or a diverged branch, resolve that state before pulling; do not reset
or overwrite the existing checkout.

The committed snapshots are ready to use. To deliberately regenerate them:

```bash
python scripts/generate_synthetic.py
python scripts/generate_synthetic.py --check
python scripts/evaluate_synthetic.py --json
```

The generator fixes seed `20261022`, generation timestamp
`2026-10-22T00:00:00Z`, schema `aggregate-1` and generator `synthetic-1.0.0`.
Each snapshot contains exactly these four files:

- `facility_registry.csv`: six facility records.
- `malaria_monthly.csv`: report versions for January 2024–December 2025.
- `reporting_log.csv`: receipt and acceptance/withdrawal state per report version.
- `manifest.json`: schema field order, raw row counts, exact byte hashes and
  order-independent canonical-content hashes.

There are 144 **expected** facility-months per snapshot. Revisions add raw rows;
missing-report fixtures deliberately contain fewer observed rows. The missing
baseline fixture has 23 observed months within the declared 24-month scope.
The existing `data/synthetic/probe/` remains unchanged and separately verifiable.

## Evaluator-only scenario catalogue

This guide and `evals/` are developer/evaluator materials. Source CSVs and manifests
use opaque dataset IDs and carry no scenario names or expected conclusions.

| Dataset ID | Fixture | Monthly / log rows | Evaluation cases |
|---|---|---:|---|
| `fx_10a7c921` | Expanded testing | 144 / 144 | E01 |
| `fx_32e8b610` | Reporting revision | 145 / 145 | E02 |
| `fx_47c9d203` | Unexplained increase | 144 / 144 | E03 |
| `fx_58f1a946` | Mixed revision and residual | 145 / 145 | E04 |
| `fx_6b2d801e` | Missing comparison month | 138 / 138 | E05 |
| `fx_7c3e912f` | True zero target tests | 144 / 144 | E06 |
| `fx_8d4fa230` | Positive greater than tested | 144 / 144 | E07 |
| `fx_9e50b341` | Conflicting primary key | 145 / 144 | E08 |
| `fx_a061c452` | Revision after/before cutoff | 145 / 145 | E09_before, E09_after |
| `fx_b172d563` | Latest version invalid | 145 / 145 | E10_invalid |
| `fx_c283e674` | Latest version withdrawn | 145 / 145 | E10_withdrawn |
| `fx_d394f785` | One target report missing | 143 / 143 | E11 |
| `fx_e4a50896` | Orphan log | 144 / 145 | E12_orphan |
| `fx_f5b619a7` | Unknown facility | 144 / 144 | E12_unknown |
| `fx_06c72ab8` | Missing positive count | 144 / 144 | E13 |

The four main scenarios compare October and November 2025 across all six facilities:

| Fixture | Comparison tested / positive | Target canonical tested / positive | Positivity change |
|---|---:|---:|---:|
| Expanded testing | 400 / 80 | 800 / 160 | 20% → 20%; 0 pp |
| Reporting revision | 500 / 100 | 500 / 100 | 20% → 20%; 0 pp |
| Unexplained increase | 500 / 100 | 500 / 175 | 20% → 35%; +15 pp |
| Mixed | 500 / 100 | 500 / 125 | 20% → 25%; +5 pp |

Revision raw target totals are 600 tested / 120 positive; mixed raw target totals
are 600 / 145. Canonical selection retains the latest **observed** version; it does
not sum versions. Mixed data leave a residual increase of 25 positives after the
extra old version's 20 positives are removed.

## Independent answers and reference checks

`evals/scenario_answers.json` contains manually specified expectations, acceptable
interpretations and prohibited claims. The generator never reads that file.
`evals/reference.py` independently reads/validates published bytes and implements
bounded fixture calculations; it never imports the generator or answers.
`evals/evaluate.py` compares the two, including required and forbidden version IDs.
No model produces these answers, and the harness does not evaluate model reasoning.

The evaluator checks 16 cases over 15 snapshots. Tests additionally cover shuffled
rows (E14), duplicate-preserving hashes, weighted rather than averaged positivity,
cutoff inclusivity, old-version late arrival, joins, tampering and staging/packaging.
E15–E23 (service failures, agent authority, memory and worker behaviour) remain
planned. Invalid fixture records intentionally trigger findings; successful fixture
evaluation means the expected failure handling occurred, not that those source
records passed all integrity checks.

An orphan log has no known facility/month; the reference conservatively blocks
aggregate claims across the selected scope. Unknown-facility records likewise
block aggregates. Conflicting report keys block their report; invalid, missing or
withdrawn latest records reduce analytical completeness. Output shows all-available
and matched-facility totals separately. Raw diagnostics omit invalid/withdrawn
versions and disclose findings. No missing observation is converted to zero.

This evaluator is a small reference for the constructed suite. It is not the future
runtime gateway, evidence-ID catalogue, generic real-data validator or approved
clinical workflow. The data contract defines the broader implementation obligations.

## Stage source files for the next live check

Start with the revision snapshot: it exercises all three tables and version-aware
arithmetic. Create a new destination, for example:

```bash
python scripts/stage_synthetic.py \
  --dataset fx_32e8b610 \
  --destination "$HOME/afyaevidence-upload/fx_32e8b610"
```

The script verifies hashes, copies only the three CSVs and manifest, and refuses an
existing destination. It never copies evaluator keys or connects to Zetaris.
Upload the **three CSVs** through NDP File System using the file-store route already
verified on your instance. Keep the manifest locally for reconciliation. Choose a
new source folder and a separate logical database/table namespace; inspect existing
objects first. Do not replace `AFYAEVIDENCE.facility_registry`, which currently holds
the verified `fx_probe_v1` fixture. Register the three tables with comma delimiter,
header `true` and `inferSchema=false`; preview each source before creating it.

The next live acceptance is three bounded JDBC reads, full table hash/count
reconciliation, a non-multiplying version-key join and parity with the reference.
The current `verify_zetaris.py` intentionally remains the six-row **probe** verifier;
it does not verify these monthly snapshots. A three-table verifier is the next
integration slice, rather than an untested claim in this increment.

## Runtime packaging and isolation

The runtime wheel includes only `src/afyaevidence`; it has no third-party runtime
dependencies in this increment. `requirements.lock` records that empty dependency
set; `pyproject.toml` pins the build backend. The existing local JDBC environment
is separate and is not modified or falsely represented by this lock.

```bash
python -m pip wheel . --no-deps --wheel-dir dist
python scripts/check_runtime_package.py dist/afyaevidence-0.1.0-py3-none-any.whl
```

The wheel guard uses an explicit member allowlist. Evaluator scripts and the
source-only staging tool run from a development checkout, not from this wheel.
Future application images must mount only staged source files and must not copy
repository-root docs, tests or `evals/`. Wheel exclusion is verified now; image/tool
isolation must be checked again when those components exist. Public Git access is
not a secrecy guarantee, so the future agent must have no filesystem or arbitrary
network retrieval tool.

## Recorded verification

Local checks on 22 October 2026: 37 tests passed, 16 fixture cases passed, byte
reproducibility passed, and the built wheel passed its exclusion guard. These results
establish behaviour on this synthetic suite only. GitHub-hosted CI is separate;
the existing account-level Actions restriction previously prevented jobs starting.

The operator reported the original live probe output:

```text
ZETARIS_CONNECTION=PASS
ZETARIS_PROJECT_TABLE=PASS
ZETARIS_PROJECT_ROWS=6
```

That establishes the six-row project-table milestone on the operator's machine.
The new three-table snapshots, Meterless H-MEM, model and integrated agent have
**not** been exercised live by this increment.
