# AfyaEvidence

An evidence-grounded malaria reporting investigation agent for a district reporting reviewer.

**Status:** source contracts, six-row JDBC probe and reproducible synthetic-data suite implemented. The operator has reported successful live reconciliation of `AFYAEVIDENCE.facility_registry` (six probe rows). Fifteen 24-month snapshots, three CSVs per snapshot and 16 independent evaluator cases are available. The operator has also reported full three-table live hash/join/reference verification. Runtime immutable snapshots, fixture/JDBC gateways and deterministic scoped analysis are implemented; the operator has reported the runtime CLI's live Zetaris PASS. The operator also reported pinned H-MEM persistence/provenance/scope/chronology/retry PASS. The bounded agent loop, strict actions, server-rendered referenced briefs, scripted and Ollama providers, model probe and combined operator CLI are implemented. Actual model capability and the combined real-model run remain pending; the authenticated review interface is not implemented.

Repository: [buriro-ezekia/afyaevidence](https://github.com/buriro-ezekia/afyaevidence).

## First runnable milestone

Use your **existing checkout** in the Ubuntu VS Code terminal:

```bash
git fetch origin
git switch codex/architecture-and-jdbc-probe
git pull --ff-only origin codex/architecture-and-jdbc-probe
python scripts/generate_probe.py --check
python scripts/verify_zetaris.py --check-fixture
python scripts/generate_synthetic.py --check
python scripts/evaluate_synthetic.py
python scripts/verify_zetaris_snapshot.py --check-fixture
python scripts/check_agent.py
python scripts/analyse_snapshot.py --mode fixture --snapshot data/synthetic/fx_32e8b610
python -m unittest discover -s tests -v
```

The full test suite requires Python 3.12+ and Node 24 in Ubuntu/WSL. Fixture calculations require no Java, credentials, new model or live database; the H-MEM tests execute the pinned local TypeScript reference without npm installs. They validate local fixtures. The [synthetic-data guide](docs/SYNTHETIC_DATA.md) covers regeneration, scenario IDs, independent answers, staging and package isolation. If Git reports local changes/divergence, resolve them before pulling; do not reset the existing checkout.

The original [first data-access guide](docs/FIRST_DATA_ACCESS.md) retains the exact Zetaris JDBC probe. A failed live query never falls back to local replay.

## Product contract

Given one fictional district, two reporting months and a fixed observation cutoff, investigate why reported confirmed malaria episodes differ. Retrieve aggregate reporting evidence through Zetaris, calculate transparent comparisons, examine alternative explanations and prepare a source-linked brief for human review.

Initial scope: six fictional facilities, January 2024 to December 2025, three source tables, three core scenarios plus edge cases. There are 144 expected facility-months; report revisions can increase raw row counts. All data is synthetic. The prototype does not diagnose patients, declare outbreaks, recommend treatment or edit reporting records.

## Design documents

| Document | Implementation purpose |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | Components, dependency boundaries, investigation lifecycle, deployment and failure handling |
| [First data access](docs/FIRST_DATA_ACCESS.md) | Six-row JDBC probe and operator-reported live acceptance |
| [Bounded agent loop](docs/AGENT_LOOP.md) | Approved tools, strict actions, call budgets, referenced rendering and actual-model checks |
| [Meterless H-MEM](docs/HMEM_BRIDGE.md) | Pinned actual reference, scoped reviewed-note persistence, provenance and outbox retries |
| [Runtime analysis](docs/RUNTIME_ANALYSIS.md) | Immutable snapshots, explicit fixture/JDBC gateways, scoped facts and JSON receipts |
| [Three-table verification](docs/VERIFY_SNAPSHOT.md) | Exact live JDBC hashes, join and reference parity |
| [Synthetic data](docs/SYNTHETIC_DATA.md) | Fifteen reproducible snapshots, evaluator answers, checks and source-only staging |
| [Data contract](docs/DATA_CONTRACT.md) | Three source tables, observation cutoffs, revision resolution and indicator semantics |
| [Tool and API contracts](docs/CONTRACTS.md) | Model-visible tools, evidence/brief structures, human review and API endpoints |
| [Evaluation](docs/EVALUATION.md) | Scenario answers, edge cases and separate fixture/live acceptance gates |
| [Implementation backlog](docs/IMPLEMENTATION.md) | Ordered GitHub issues with acceptance criteria |
| [Integration decisions](docs/adr/0001-local-runtime-and-adapters.md) | Technology choices, sponsor limitations and deferred scope |
| [Source register](docs/SOURCES.md) | Official technical references and observed source revisions |

## Start implementation

The original probe and full three-table JDBC verifier passed on the operator's machine. Next run the packaged [runtime analysis layer](docs/RUNTIME_ANALYSIS.md) against the registered revision source and retain its private snapshot and scoped analysis receipts.

The architecture tree remains a target: source contracts, generation and evaluator arithmetic exist; the runtime snapshot/analysis package is implemented; the pinned memory bridge is implemented; the bounded model loop is implemented; authenticated UI and worker service remain planned. The existing working JDBC environment remains separate. Local checks: 107 tests, 16 fixture cases, reproducible bytes, three-table verifier offline preflight and wheel exclusion passed. The [three-table JDBC verifier](docs/VERIFY_SNAPSHOT.md) passed on the operator's machine. The [runtime analysis CLI](docs/RUNTIME_ANALYSIS.md) also passed on the operator's machine. The H-MEM bridge also passed on the operator's machine. Next run the [actual-model probe and combined agent command](docs/AGENT_LOOP.md). GitHub-hosted CI previously could not start because of an account-level Actions restriction; no hosted PASS is claimed.

## Development boundaries

The application queries Zetaris with the supplied Zetaris driver JAR, not a Hive or Spark driver. It does not start Spark. Source setup is an operator action separate from the agent. Model-generated SQL, shell execution and source-data writes are outside the agent's tool surface.

Meterless H-MEM is the proposed memory integration. A model-provider adapter is a separate concern. Its deterministic reference uses mock embeddings and JSON persistence, so integration does not establish production readiness. The optional Meterless Runtime provider requires its own availability/authentication/capability tests.

No secret, proprietary JAR, real health record or local database belongs in Git. Existing repositories inform design; copied code requires licence review, attribution and a clear record of pre-existing work. Choose a licence for original project code before publishing it; this pack does not make that decision for the owner.
