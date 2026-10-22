# AfyaEvidence

An evidence-grounded malaria reporting investigation agent for a district reporting reviewer.

**Status:** synthetic source contracts, immutable snapshots, deterministic analysis, the pinned H-MEM bridge and bounded agent CLI are implemented. Prior operator-reported live Zetaris gates remain recorded. The new explicit CPU profile performs one model-selected follow-up and one brief-only request, with smaller phase contexts and a reserved final-request allowance. Actual `qwen2.5:1.5b` inference on fixture data produced a valid review-only candidate in two requests (201.28 seconds). The current combined live verification is **BLOCKED at Zetaris login**, including with the operator-supplied credential; no combined PASS is claimed. See [CPU verification](docs/CPU_VERIFICATION.md) for actual checks, preserved failures and the remaining gate. The authenticated review interface and deployment remain unimplemented.

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

The architecture tree remains a target: source contracts, generation, evaluator arithmetic, runtime analysis, the pinned memory bridge and bounded model loop are implemented; the authenticated UI and worker service remain planned. Deterministic checks, both scripted execution profiles and package isolation pass. Actual CPU model inference passes with fixture data; combined Zetaris/Ollama/H-MEM acceptance remains blocked at JDBC login in this verification. See [CPU verification](docs/CPU_VERIFICATION.md) and the [copyable operator commands](docs/AGENT_LOOP.md). No hosted CI PASS is claimed.

## Development boundaries

The application queries Zetaris with the supplied Zetaris driver JAR, not a Hive or Spark driver. It does not start Spark. Source setup is an operator action separate from the agent. Model-generated SQL, shell execution and source-data writes are outside the agent's tool surface.

Meterless H-MEM is the proposed memory integration. A model-provider adapter is a separate concern. Its deterministic reference uses mock embeddings and JSON persistence, so integration does not establish production readiness. The optional Meterless Runtime provider requires its own availability/authentication/capability tests.

No secret, proprietary JAR, real health record or local database belongs in Git. Existing repositories inform design; copied code requires licence review, attribution and a clear record of pre-existing work. Choose a licence for original project code before publishing it; this pack does not make that decision for the owner.
