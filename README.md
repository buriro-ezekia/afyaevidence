# AfyaEvidence

**An evidence-led investigation assistant for synthetic district-level malaria reporting.**

AfyaEvidence helps a district reporting reviewer understand why malaria indicators have changed. It checks report revisions, missing records and testing activity, then prepares source-linked findings for **human review**. The current implementation uses fictional aggregate data; it is not a clinical tool or a deployed surveillance service.

## Where to find the working prototype

The developed application currently lives on a separate, tested integration branch rather than `main`:

- **[Project README and safe setup](https://github.com/buriro-ezekia/afyaevidence/blob/work/keycloak-live-acceptance/README.md)**
- **[Hackathon judges' guide and architecture](https://github.com/buriro-ezekia/afyaevidence/blob/work/keycloak-live-acceptance/docs/HACKATHON_JUDGES_GUIDE.md)**
- **[Source and evidence freeze](https://github.com/buriro-ezekia/afyaevidence/blob/work/keycloak-live-acceptance/docs/HACKATHON_PHASE1_FREEZE.md)**
- **[Frozen, demonstrated source revision](https://github.com/buriro-ezekia/afyaevidence/tree/80fbb9fd52c2ecc0b3f987e476e3908c6fbc4a71)**

The branch has passed local synthetic regression testing, and CircleCI pipeline #26 succeeded on its documented auditor revision across Python 3.12–3.14. Live Zetaris, local Ollama and the pinned Meterless H-MEM reference were demonstrated separately in an operator-reported integrated investigation; fixture-only CI must not be confused with external-service attestation.

## Why development remains on a branch

Earlier pull requests contain identity, offline evidence and managed-worker changes that have not been promoted to the default branch. Keeping them separate preserves their review and release boundaries. This landing page makes the working code easy to find **without merging unreviewed deployment or security changes**.

The prototype's findings always require a human reviewer. Production release remains blocked by outstanding security and governance work.

For the Open Agent Hackathon 2026, assess the working synthetic prototype through the linked implementation and judges' guide. No patient data or source credentials are published here.
