# First data-access milestone

This milestone proves that AfyaEvidence can retrieve its own source records through Zetaris. It is deliberately smaller than the 24-month malaria generator. The source-access probe has six fictional facilities, no malaria counts and no personal data.

## What is implemented

- `scripts/generate_probe.py`: deterministic probe CSV and byte/canonical-content manifest.
- `scripts/verify_zetaris.py`: fixture validation, read-only metadata discovery and exact project-table reconciliation.
- Standard-library tests and fixture-only GitHub CI. Live JDBC tests do not run against a GitHub runner's localhost.

This work does not register a source, create a database or modify the existing Zetaris containers. The operator subsequently reported `ZETARIS_CONNECTION=PASS`, `ZETARIS_PROJECT_TABLE=PASS` and `ZETARIS_PROJECT_ROWS=6` for `AFYAEVIDENCE.facility_registry` on 22 October 2026. This is operator-reported evidence, not a run in the remote development environment. The broader three-table gate remains pending.

## 1. Use Ubuntu and the existing JDBC environment

Use the existing checkout in your Ubuntu VS Code terminal. The README contains the feature-branch update commands; no new clone is needed.

Your existing environment from the successful JDBC check may be activated with:

```bash
source ~/zetaris-setup/zetaris-platform/.venv-jdbc/bin/activate
```

If that environment is elsewhere, activate its actual path. The verifier imports `jaydebeapi` only for live access. Use the already working Java/JayDeBeApi/JPype setup rather than replacing it during this spike. Dependency locking for the application follows after this setup is recorded and tested.

Check the probe independently:

```bash
python scripts/generate_probe.py --check
python scripts/verify_zetaris.py --check-fixture
python -m unittest discover -s tests -v
```

These commands require no Java/JAR/network, query no database and cannot establish live integration success.

## 2. Discover available objects read-only

Use the absolute path to the matching JAR you already tested. If the JAR is at the earlier project-relative location, resolve it explicitly:

```bash
export ZETARIS_JDBC_JAR="$(realpath ~/zetaris-setup/zetaris-platform/jdbc/ndp-jdbc-driver-2.4.3.1-7eff043-driver.jar)"
python scripts/verify_zetaris.py --discover
```

If `realpath` reports that the file is missing, stop and locate the actual supplied file; do not substitute another driver. The verifier prompts for the Zetaris user ID and password unless their values are already supplied locally. Enter the same user ID, preserving case, that passed the earlier JDBC check. Do not paste credentials into GitHub or chat.

Discovery executes `SELECT 1`, `SHOW LIGHTNING DATABASES` and `SHOW DATASOURCES` separately. Empty lists are legitimate. A connection PASS does not imply that the project table exists.

## 3. Register the six-row source using a verified route

Source file: `data/synthetic/probe/facility_registry.csv`.

Choose a route supported by this installation, inspect existing objects and preview its setup statements before executing them:

- A reachable file source, following the current Zetaris filestore guide. The existing official examples demonstrate S3/S3-compatible paths; a CSV in the WSL checkout is not automatically a readable path inside the Zetaris driver container.
- A dedicated project database registered as a source, if that route is available. Keep it separate from Zetaris's internal metadata PostgreSQL database.

The exact object name, source registration SQL, filesystem mount or storage endpoint are instance-specific and intentionally not guessed in this repository. The operator provisions the source; the verifier and future agent remain read-only. Record the successful recipe and any failed feature assumptions in an integration note.

Required resulting columns are `dataset_id`, `facility_id`, `district_id`, `facility_type`, `active_from`, `active_to`. Empty active-to cells mean no end date; normalise null/empty string accordingly. Preserve `F001`–`F006` as strings.

## 4. Reconcile actual rows

Set the actual qualified table name once it is registered, for example replacing `YOUR_SOURCE.YOUR_TABLE` below:

```bash
python scripts/verify_zetaris.py --table YOUR_SOURCE.YOUR_TABLE
```

The verifier uses the fixed SELECT column list, a fixed dataset filter and a seven-row cap to detect duplicate/extra rows. It sends one statement per call and compares all six retrieved records with the repository fixture. It uses `com.zetaris.lightning.jdbc.LightningDriver` and your supplied JAR, never a Hive/Spark driver, and does not start Spark.

Only a successful real source query and exact reconciliation may print:

```text
ZETARIS_CONNECTION=PASS
ZETARIS_PROJECT_TABLE=PASS
```

Missing configuration/dependencies are BLOCKED; query or data mismatches fail. A missing or inaccessible source is not repaired by a local CSV fallback. The script does not impose a driver-independent hard query timeout; interrupt a stalled local probe and report it rather than leaving it unattended.

## Completion record

Record the actual code commit, Python/Java/JayDeBeApi/JPype versions, driver checksum, qualified source name, registration route, row count, fixture hash and real output without credentials. Do not mark Issue 01 complete until project-table reconciliation succeeds. The broader three-table join and version-aware aggregate gates follow when the monthly fixture tables are implemented.

## Observed successful registration route

The operator created logical database `AFYAEVIDENCE`, uploaded the CSV through NDP
File System, and selected it under `/file-store` in Create Table → File Store.
Settings: CSV, NDP File System, table `facility_registry`, delimiter comma,
`header=true`, `inferSchema=false`. The table appeared in Metadata and subsequently
passed the exact six-row JDBC reconciliation.

Earlier direct paths `/home/zetaris/customer-data/afyaevidence/probe/facility_registry.csv`
and its `file:///` form were rejected with `Invalid file path to access`, despite
the file being readable inside the driver container. Do not repeat that failed
registration assumption or replace the existing source while loading new snapshots.
The exact backend URI and permission cause were not established.

Full synthetic snapshots and their separate namespace/staging procedure are in
[SYNTHETIC_DATA.md](SYNTHETIC_DATA.md). The probe script remains probe-specific.
