# AfyaEvidence

An evidence-grounded malaria reporting investigation agent for a district reporting reviewer.

**Status:** architecture and source-access probe. The six-facility synthetic fixture, generator and read-only JDBC verifier are implemented. The investigation agent, monthly malaria scenarios and H-MEM integration remain planned. The user's separate local Zetaris installation and `SELECT 1` JDBC test have passed; this project's actual table reconciliation must still run on that machine.

Repository: [buriro-ezekia/afyaevidence](https://github.com/buriro-ezekia/afyaevidence).

## First runnable milestone

While the bootstrap pull request is open, start from its feature branch in Ubuntu:

```bash
git clone --branch codex/architecture-and-jdbc-probe --single-branch https://github.com/buriro-ezekia/afyaevidence.git ~/afyaevidence
cd ~/afyaevidence
python3 scripts/generate_probe.py --check
python3 scripts/verify_zetaris.py --check-fixture
python3 -m unittest discover -s tests -v
```

Use a new destination if `~/afyaevidence` already exists; do not overwrite an existing checkout. These checks require no Java, external packages, credentials or live database. They validate only the local synthetic probe.

Next follow [First data access](docs/FIRST_DATA_ACCESS.md) to activate the existing JDBC environment, discover sources read-only, register the tiny fixture through a supported route and reconcile real returned rows. The verifier does not create or change a source. A live failure cannot fall back to local fixture results.

## Product contract

Given one fictional district, two reporting months and a fixed observation cutoff, investigate why reported confirmed malaria episodes differ. Retrieve aggregate reporting evidence through Zetaris, calculate transparent comparisons, examine alternative explanations and prepare a source-linked brief for human review.

Initial scope: six fictional facilities, January 2024 to December 2025, three source tables, three core scenarios plus edge cases. There are 144 expected facility-months; report revisions can increase raw row counts. All data is synthetic. The prototype does not diagnose patients, declare outbreaks, recommend treatment or edit reporting records.

## Design documents

| Document | Implementation purpose |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | Components, dependency boundaries, investigation lifecycle, deployment and failure handling |
| [First data access](docs/FIRST_DATA_ACCESS.md) | Runnable six-row probe, local JDBC discovery and pending source registration/reconciliation |
| [Data contract](docs/DATA_CONTRACT.md) | Three source tables, observation cutoffs, revision resolution and indicator semantics |
| [Tool and API contracts](docs/CONTRACTS.md) | Model-visible tools, evidence/brief structures, human review and API endpoints |
| [Evaluation](docs/EVALUATION.md) | Scenario answers, edge cases and separate fixture/live acceptance gates |
| [Implementation backlog](docs/IMPLEMENTATION.md) | Ordered GitHub issues with acceptance criteria |
| [Integration decisions](docs/adr/0001-local-runtime-and-adapters.md) | Technology choices, sponsor limitations and deferred scope |
| [Source register](docs/SOURCES.md) | Official technical references and observed source revisions |

## Start implementation

Complete the first milestone described in [Implementation](docs/IMPLEMENTATION.md): prove that one synthetic project table can be retrieved through the existing Zetaris JDBC connection. Determine the actual supported data-registration route before investing in the interface or model loop. The source-access probe prepares this check; it does not yet establish the broader three-table/versioned-report integration.

The full repository tree shown in the architecture is a target layout. Only the documented probe and tests are implemented so far. Record and lock the already working JDBC environment after verifying it on Ubuntu/WSL; do not invent package pins or replace it during the access spike. The fixture CI uses standard-library Python and pinned GitHub Actions.

## Development boundaries

The application queries Zetaris with the supplied Zetaris driver JAR, not a Hive or Spark driver. It does not start Spark. Source setup is an operator action separate from the agent. Model-generated SQL, shell execution and source-data writes are outside the agent's tool surface.

Meterless H-MEM is the proposed memory integration. A model-provider adapter is a separate concern. Its deterministic reference uses mock embeddings and JSON persistence, so integration does not establish production readiness. The optional Meterless Runtime provider requires its own availability/authentication/capability tests.

No secret, proprietary JAR, real health record or local database belongs in Git. Existing repositories inform design; copied code requires licence review, attribution and a clear record of pre-existing work. Choose a licence for original project code before publishing it; this pack does not make that decision for the owner.
