# AfyaEvidence

**Understanding changes in malaria reporting, with evidence that people can check.**

AfyaEvidence is an experimental AI investigation assistant for district-level malaria reporting. It helps a reviewer answer a practical question: *when reported malaria indicators change, what does the available reporting evidence actually explain?*

A rise in reported positives does not always mean the underlying situation has changed. A late correction, a withdrawn report, a missing facility or more people being tested can alter the figures. AfyaEvidence examines those possibilities before preparing a traceable explanation for a human reviewer.

The current project works with **fictional facilities and synthetic aggregate records**. It is not deployed disease surveillance, a diagnostic tool or a system that declares outbreaks.

## What the agent does

For a selected district, two months and an observation cutoff, AfyaEvidence:

1. Collects a verified snapshot of facility reporting, including the facility register and report-version log.
2. Checks completeness, conflicting records, missing values and revised submissions.
3. Compares raw report totals with accepted, version-aware figures using deterministic calculations.
4. Uses a bounded agent to investigate plausible explanations and draft findings linked to the evidence.
5. Leaves the candidate **awaiting human review**. It cannot approve its own findings or alter source records.

The distinction matters. If an apparent increase comes from counting an older report alongside its replacement, the reviewer should see that clearly. Where a change remains unexplained after the available checks, the system says so rather than assigning a cause.

## Open Agent Hackathon 2026

**Submission track:** The Agent That Can Explain Why  
**Project scope:** Synthetic malaria reporting investigations  
**Source revision demonstrated:** [80fbb9f](https://github.com/buriro-ezekia/afyaevidence/tree/80fbb9fd52c2ecc0b3f987e476e3908c6fbc4a71)  
**Development branch:** `work/keycloak-live-acceptance`  
**Submission status:** Draft; no HackOS submission confirmation recorded.

The [judges' guide](docs/HACKATHON_JUDGES_GUIDE.md) provides a short walkthrough, architecture, sponsor-technology boundaries, verification evidence and limitations. For the exact source/receipt hashes and CI history, see the [Phase 1 freeze record](docs/HACKATHON_PHASE1_FREEZE.md).

### How the sponsor technologies contribute

| Technology | Role in the demonstrated workflow |
| --- | --- |
| **Zetaris** | Reads registered synthetic CSV-backed reporting tables through reviewed JDBC access. The application does not grant the model arbitrary SQL access. |
| **Meterless H-MEM reference** | Provides a pinned, locally running Node 24 memory bridge for scoped historical review context, with provenance and chronological limits. |
| **Ollama** | Runs the local model used by the bounded agent to select allowed investigation actions and propose an explanation. |
| **Python analysis and review controls** | Own deterministic metrics, evidence validation, source immutability and the human decision boundary. |

The successful integrated demonstration used Zetaris, Ollama and the pinned H-MEM reference. **No historical memory notes were recalled in that run**; the memory connection worked, but those notes did not contribute to its explanation. Do not confuse this with independent verification of external service logs.

## Demonstrated results

Results below are based on the operator's local execution and CircleCI screenshot, not a production assessment.

| Check | Observed evidence |
| --- | --- |
| Full local regression, 26 October 2026 | **335 tests passed** in 71.306 seconds |
| Synthetic evaluation | **15** reproducible snapshots, **16** evaluation scenarios |
| Agent fixture evaluation | **32** scripted runs across standard and CPU profiles |
| Hosted verification | CircleCI **pipeline #26**: Python 3.12, 3.13 and 3.14 all passed at commit `d3941a5` |
| Integrated demonstration, 25 October | Actual Zetaris + Ollama + H-MEM operation reported **PASS**; two model calls, five tool calls, zero repairs |
| Candidate outcome | `reporting_artefact_supported`, `awaiting_human_review` |
| Receipt integrity | Read-only source freeze **PASS**; previous integrated receipt SHA-256 matched the preserved witness |

The automated fixture suite does **not** call live Zetaris, Ollama or H-MEM services. The earlier integrated operator receipt and redacted witness document that separate demonstration. The local receipt is **not** an independent network attestation.

## Try the synthetic checks

The safest starting point is the deterministic fixture suite. It requires no patient records, Zetaris credentials or live model endpoint.

Requirements: **Ubuntu/WSL**, **Python 3.12 or later**, **Node.js 24** and the optional Python identity dependencies. From a fresh clone of this development branch:

```bash
git clone --branch work/keycloak-live-acceptance \
  https://github.com/buriro-ezekia/afyaevidence.git
cd afyaevidence

python3 -m venv .venv
source .venv/bin/activate
python -m pip install '.[identity]'

# With nvm installed and Node.js 24 available:
source "$HOME/.nvm/nvm.sh"
nvm use 24

python scripts/verify_identity_worker.py --fixtures
python -m pip check
```

The verifier runs the Python tests, deterministic data and agent checks, H-MEM reference tests and isolated package checks. It prints `IDENTITY_WORKER_TESTS=PASS` only when all included checks succeed, and saves local logs in `runtime/identity-verification-…`.

For a smaller, fully scripted agent exercise:

```bash
python scripts/run_agent.py \
  --data-mode fixture \
  --snapshot data/synthetic/fx_32e8b610 \
  --model-provider scripted \
  --output runtime/agent-fixture-demo.json
```

Choose a different output filename if it already exists. The scripted provider verifies the investigation workflow; **it is not a test of live language-model reasoning**.

To reproduce the real Zetaris–Ollama–H-MEM integration, consult the [hackathon readiness runbook](docs/HACKATHON_SUBMISSION_READINESS.md). It requires your own configured services, JDBC driver and private local credentials. The application never substitutes fixture data when a live source fails.

## Architecture in brief

```mermaid
flowchart TD
    U["District reporting reviewer"] --> Q["Question and observation cutoff"]
    Q --> S["Verified synthetic reporting snapshot"]
    Z["Zetaris: registered CSV-backed tables"] -->|Reviewed JDBC reads| S
    S --> C["Deterministic quality and indicator checks"]
    C --> A["Bounded investigation agent"]
    O["Ollama local model"] -->|Structured action proposals| A
    H["Meterless H-MEM reference"] -->|Scoped prior review context| A
    A --> E["Evidence-linked candidate brief"]
    E --> R["Human review required"]
    E --> B["Read-only offline evidence briefcase"]
```

The host controls tool permissions, calculations and evidence references. A model cannot execute arbitrary SQL, edit reporting records, approve a candidate or turn historical memory into a current indicator.

The [architecture and demonstration guide](docs/HACKATHON_JUDGES_GUIDE.md) explains the current implementation without relying on the older proposed architecture diagram.

## Offline reading and security limits

A completed synthetic investigation can be exported as a **read-only HTML evidence briefcase** for viewing without connectivity. Signed offline package experiments add hash checks, signatures and publisher-registry verification. They do **not** enable offline authentication, source refresh, clinical approval or synchronisation of reviewer decisions.

The repository also contains experimental Keycloak-backed reviewer identity and supervised worker components. Local access-control tests are not production authorisation.

**Production release remains blocked.** The candidate Keycloak container still has reported security findings; independent security assurance, deployment controls and clinical governance have not been completed. Do not use the prototype for patient care or real public-health decisions.

## Repository map

| Location | Purpose |
| --- | --- |
| `src/afyaevidence/` | Analysis contracts, agent, adapters and local review services |
| `data/synthetic/` | Reproducible fictional reporting snapshots |
| `evals/` | Independent scenario expectations; not supplied to the agent |
| `bridges/hmem/` | Pinned Meterless H-MEM reference and attribution |
| `scripts/` | Verification, demonstrations, evidence export and audits |
| `tests/` | Regression and security-boundary tests |
| `docs/` | Technical design, provenance, security and operator runbooks |
| `.circleci/config.yml` | Hosted synthetic-only verification matrix |

## Branch and contribution policy

The `main` branch currently contains the minimal repository starting point. The complete prototype sits on a **draft integration branch** because earlier feature and identity/security pull requests have not been merged. This does not mean that the working application is absent; it means the branch has not been promoted to the default branch.

For the hackathon, use the pinned source link above and this branch's documentation. Any later promotion to `main` should follow a source, licence, sensitive-file and security review, then a deliberate merge. A successful hackathon demonstration is not a production release.

All fictional data, code and results should be described accurately. Please use **UK English**, clear professional language and explicit distinctions between `PASS`, `BLOCKED` and `NOT_RUN` when contributing documentation or test evidence.

## Further reading

- [Judges' quick guide](docs/HACKATHON_JUDGES_GUIDE.md)
- [Phase 1 evidence freeze](docs/HACKATHON_PHASE1_FREEZE.md)
- [Agent design and investigation controls](docs/AGENT_LOOP.md)
- [Synthetic data and evaluation](docs/SYNTHETIC_DATA.md)
- [Meterless memory bridge](docs/HMEM_BRIDGE.md)
- [Offline evidence briefcase](docs/OFFLINE_EVIDENCE_BRIEFCASE.md)
- [CircleCI verification](docs/CIRCLECI_SYNTHETIC_SETUP.md)
- [Residual Keycloak security](docs/KEYCLOAK_RESIDUAL_SECURITY.md)

**AfyaEvidence's aim is straightforward: make the evidence behind an unusual reporting change easier to inspect, while keeping the decision with the person responsible for it.**
