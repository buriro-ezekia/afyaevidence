# Verify the three-table Zetaris snapshot

The operator has registered the revision snapshot `fx_32e8b610` under logical
database `AFYAEVIDENCE_REVISION` using NDP File System. Operator-reported SQL
Workspace results show registry/monthly/log row counts of 6/145/145, both versions
of report `R202511001` with the expected counts and receipt times, and exactly 145
rows from the full version-key join. Those UI results do not themselves establish
JDBC content reconciliation.

## Update the existing checkout

Run in the Ubuntu VS Code terminal already in this repository. Leave the earlier
local-change stash saved; do not apply it over this implementation.

```bash
git pull --ff-only origin codex/architecture-and-jdbc-probe
python scripts/verify_zetaris_snapshot.py --check-fixture
python -m unittest discover -s tests -v
```

If Git reports local modifications, stop and inspect them before updating; never
reset or discard local work. Offline preflight requires Python 3.12+ and no external
packages, Java or credentials. It prints `ZETARIS_SNAPSHOT=NOT_RUN`, not live PASS.

## Run the real JDBC check

Activate the existing working environment. Use the exact supplied Zetaris JAR:

```bash
source ~/zetaris-setup/zetaris-platform/.venv-jdbc/bin/activate

python scripts/verify_zetaris_snapshot.py \
  --database AFYAEVIDENCE_REVISION \
  --dataset fx_32e8b610 \
  --as-of 2026-01-15T00:00:00Z \
  --jar "$HOME/zetaris-setup/zetaris-platform/jdbc/ndp-jdbc-driver-2.4.3.1-7eff043-driver.jar"
```

Enter the user ID with the same case and password that passed the original JDBC
probe. Password input is hidden. Existing `ZETARIS_USERNAME`, `ZETARIS_PASSWORD`,
`ZETARIS_JDBC_JAR` and `ZETARIS_JDBC_URL` settings can be used instead, or supplied
in an explicit `--env-file` containing literal KEY=value settings. Existing
environment values take precedence. Never put passwords in command arguments,
GitHub, pasted terminal output or chat. There is no password command-line option.

The default URL is `jdbc:zetaris:lightning@localhost:10000`. The driver class is
`com.zetaris.lightning.jdbc.LightningDriver`. This command starts neither a Spark
session nor a replacement driver and never creates/edits registered sources.

## What must pass

1. Validate the local three-table manifest, CSV byte hashes, canonical hashes and
   join-key integrity before connecting.
2. Execute `SELECT 1` as its own JDBC call.
3. Read all declared columns from each registered source using one SELECT per
   call and `LIMIT 2001`, with a bounded fetch loop. The independent defensive
   source cap is 2,000 rows. Do not filter by dataset: a stray row from another
   dataset in this single-snapshot namespace must cause failure.
4. Normalise returned strings, count/version integers, Booleans, dates and nulls
   using the declared schema. Compare exact row counts and canonical table hashes;
   retain duplicate multiplicity. JDBC row order is irrelevant. The CSV byte hash
   is verified locally; JDBC rows are compared with the canonical-content hash,
   never incorrectly treated as the original CSV bytes.
5. Query the actual three-table join with dataset/report/version and dataset/facility
   keys. Compare every returned value and duplicate multiplicity with the local
   expected join, not only the joined row count.
6. Run the same deterministic reference on the reconciled live rows and local CSVs
   at the same cutoff. Compare the full result, including raw/canonical totals,
   selected versions, coverage, exclusions and matched facilities.

Expected live output includes:

```text
ZETARIS_CONNECTION=PASS
ZETARIS_FACILITY_REGISTRY=PASS
ZETARIS_FACILITY_REGISTRY_ROWS=6
ZETARIS_MALARIA_MONTHLY=PASS
ZETARIS_MALARIA_MONTHLY_ROWS=145
ZETARIS_REPORTING_LOG=PASS
ZETARIS_REPORTING_LOG_ROWS=145
ZETARIS_JOIN=PASS
ZETARIS_JOIN_ROWS=145
COMPARISON_CANONICAL_TESTED=500
COMPARISON_CANONICAL_POSITIVE=100
COMPARISON_RAW_TESTED=500
COMPARISON_RAW_POSITIVE=100
TARGET_CANONICAL_TESTED=500
TARGET_CANONICAL_POSITIVE=100
TARGET_RAW_TESTED=600
TARGET_RAW_POSITIVE=120
AS_OF_UTC=2026-01-15T00:00:00Z
ZETARIS_REFERENCE_PARITY=PASS
ZETARIS_SNAPSHOT=PASS
```

The script also prints dataset/database identity, the manifest SHA-256 and each
reconciled table's canonical SHA-256. Retain this output without credentials as the
local verification receipt. Only the final `ZETARIS_SNAPSHOT=PASS` establishes that
all stages completed; earlier individual PASS lines do not override a later failure.

## Failures and limitations

Exit 0 is success, 1 is observed read/schema/reconciliation failure, and 2 is a
missing prerequisite or an interrupted run. Driver exceptions are sanitised and
identify only the failing stage. Cursor/connection close is attempted on every
path, including cancellation. There is no CSV fallback after a live failure.
Missing Java/login/service/query access cannot produce final PASS. Driver query
timeout support remains unverified: this operator CLI has no hard deadline; use
Ctrl+C if a read stalls. The future supervised application worker is separate work.

This is an operator/evaluator script in the development checkout. It imports the
bounded evaluator reference but never loads `scenario_answers.json`. It is not a
model tool or included in the runtime wheel. Reference parity complements the
independent scenario-answer tests; executing the same reference twice does not
independently prove epidemiological reasoning or every possible SQL feature.
This slice executes a real SQL join but canonicalises/aggregates in Python; it
does not claim that SQL window functions or SQL revision aggregation were tested.

The CLI accepts another opaque fixture ID, database identifier and cutoff, but
join acceptance requires structurally valid one-to-one source keys. Intentionally
conflicting/orphan fixtures remain evaluator failure-handling tests, rather than
sources expected to pass this join acceptance command.

Local validation on 22 October 2026: 52 tests passed, 16 fixture cases passed,
original/full-suite reproducibility passed, and snapshot offline preflight passed.
Fake transports tested success and failures without credentials/JVM. Actual new
live JDBC execution is NOT_RUN in this remote environment; the operator must run
the command above on their machine. Model and H-MEM integration remain pending.
