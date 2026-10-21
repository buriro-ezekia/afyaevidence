# Source register and evidence boundaries

Reviewed 21 October 2026. Official project documentation grounds adapter contracts; architectural choices and synthetic scenarios are proposed AfyaEvidence design decisions. URLs below are references, not evidence that an AfyaEvidence integration ran.

## Zetaris

- Zetaris. (n.d.). [Getting started](https://github.com/zetaris/getting-started). Reviewed root README, start guide, project paths, readiness guidance and JDBC connection material.
- Zetaris. (n.d.). [Client setup](https://github.com/zetaris/getting-started/blob/main/docs/connections/client-setup.md). Observed file blob SHA `e1b8bd6ce438f88a5cd720465c87c41dc2fcb5e8`. Documents the matching JAR, JayDeBeApi runner, local JDBC URL and one-statement execution rule. These are the selected project's connection constraints.
- Zetaris. (n.d.). [First SQL commands](https://github.com/zetaris/getting-started/blob/main/docs/connections/lightning-recipe-reference.md). Observed file blob SHA `1e658ad3fdbd34d9041ff80667fe3b6a3504eb25`. Read-only discovery and SELECT examples.
- Zetaris. (n.d.). [Parquet/CSV onboarding HOWTO](https://github.com/zetaris/getting-started/blob/main/open_data/parquet_csv/HOWTO.md). Observed file blob SHA `6adb75ff4172f869fc13c5092484ad2b5655dce7`. Examples use reachable S3/S3-compatible storage; a file on the client does not by itself establish a readable Zetaris path.
- Zetaris. (n.d.). [SQL companion](https://github.com/zetaris/getting-started/blob/main/docs/guides/zetaris-lightning-sql-companion.md). Observed file blob SHA `3793d8793f68d5de3ea021b35f95429346de8f61`. Tested behaviour is version/fixture/syntax-specific; the companion is not a promise that every SQL feature works on every instance.

The supplied JAR path/class/URL and successful SELECT 1 come from this user's actual session. They are not a new test performed while producing this pack.

## Meterless

Pin reviewed repository commit `1742dec56a66e58eef9dda2d2b865823758ca8cd` for implementation planning. Verify dependency/engine source hashes during vendoring.

- Meterless. (n.d.). [Repository map](https://github.com/Meterless/Meterless/blob/1742dec56a66e58eef9dda2d2b865823758ca8cd/llms.txt). Distinguishes engine specifications, runnable examples and the optional provider.
- Meterless. (n.d.). [H-MEM reference](https://github.com/Meterless/Meterless/blob/1742dec56a66e58eef9dda2d2b865823758ca8cd/engines/hmem/reference/README.md). Describes deterministic mock embeddings, optional JSON persistence and prototype limitations.
- Meterless. (n.d.). [Reference API facade](https://github.com/Meterless/Meterless/blob/1742dec56a66e58eef9dda2d2b865823758ca8cd/engines/hmem/reference/src/index.ts) and [memory store](https://github.com/Meterless/Meterless/blob/1742dec56a66e58eef9dda2d2b865823758ca8cd/engines/hmem/reference/src/memoryStore.ts). Reviewed actual operations and source/provenance fields; the store assigns its own memory IDs.
- Meterless. (n.d.). [Agentathon starter](https://github.com/Meterless/Meterless/blob/1742dec56a66e58eef9dda2d2b865823758ca8cd/templates/agentathon-starter/README.md). Actual H-MEM wiring requires its setup step; model inference is separate.
- Meterless. (n.d.). [Add Meterless as a provider](https://github.com/Meterless/Meterless/blob/main/docs/agent-ready/add-meterless-provider.md). Documents Runtime 0.90.0's OpenAI-compatible transport, real bearer token, headers, routing-mode discovery and health distinction. Record and verify the contract version used when implementing it.

The Meterless community hackathon guide contains older dates and a different rubric from the current organiser event page. Use the organiser page for competition rules. Do not transplant those stale details into README/submission claims.

## Domain definitions and event context

- World Health Organization. (2018). [Analysis and use of health facility data: Guidance for malaria programme managers](https://cdn.who.int/media/docs/default-source/documents/ddi/facilityanalysisguide-malaria.pdf). Provides context for test-positivity and reporting-completeness indicators. AfyaEvidence uses restricted synthetic episode definitions and no clinical thresholds. The document is not a validation of this prototype.
- GenAI.Works. (2026). [Open Agent Hackathon 2026](https://hackathon.genai.works/event/open-agent-hackathon-2026). Current organiser page: 22–27 October; Track 02 concerns evidence-backed investigation; Wildcard expressly addresses extending existing work with both sponsors. Detailed current eligibility/reuse/submission rules must be read at submission time.

No public source establishes that the proposed app is clinically effective, approved for real health data or production-ready. No such claim is made.
