# AfyaEvidence

AfyaEvidence is an evidence-driven investigation agent for synthetic district-level malaria reporting. It examines changes in aggregate indicators, distinguishes revised reports from accepted versions, checks reporting completeness and produces evidence-linked explanations for human review.

The prototype addresses a practical question: when the reported figures change, which parts of the difference are supported by the available records, and what still needs further investigation?

## How it works

The application retrieves registered synthetic CSV-backed reporting tables through Zetaris JDBC. Deterministic Python checks handle reporting quality, version-aware selection and indicator comparisons. A bounded agent using a local Ollama model proposes explanations supported by those checks. The pinned Meterless H-MEM reference provides scoped historical review context where available.

Every candidate brief remains awaiting human review. The agent cannot modify source reports, approve its own work or declare an outbreak.

## Demonstration and implementation

- [Working implementation and setup](https://github.com/buriro-ezekia/afyaevidence/tree/work/keycloak-live-acceptance)
- [Investigation architecture and example](https://github.com/buriro-ezekia/afyaevidence/blob/work/keycloak-live-acceptance/docs/HACKATHON_JUDGES_GUIDE.md)
- [Open Agent Hackathon 2026 video](https://youtu.be/h3Reux-_e7A)
- [Verification evidence and source revisions](https://github.com/buriro-ezekia/afyaevidence/blob/work/keycloak-live-acceptance/docs/HACKATHON_PHASE1_FREEZE.md)

The working application is maintained on `work/keycloak-live-acceptance`; its feature and security changes have not been merged into `main`.

## Verification and limitations

The operator reported 335 passing local tests, covering 15 reproducible synthetic snapshots, 16 evaluation scenarios and 32 scripted agent executions. CircleCI pipeline #26 passed its Python 3.12, 3.13 and 3.14 jobs at revision `d3941a5`. These checks used synthetic fixtures and did not call live sponsor services.

A separate integrated run was reported successful using Zetaris, Ollama and the Meterless H-MEM reference. No historical memory notes were recalled in that run. Its preserved receipt and witness are local evidence, not independent external-service attestation.

The video is an illustrated explanation of the synthetic workflow and reported results, not footage of a live execution. All facilities and reporting records in the demonstration are fictional.

The prototype is not a medical diagnostic tool or an operational disease-surveillance service. Production release remains blocked pending security assurance and governance review. Offline evidence exports are read-only and do not enable authentication or approval while disconnected.
