# ADR 0001: local modular application with bounded adapters

Status: proposed; accepted as the implementation baseline when repository work starts.

## Context

The user has a working Docker Desktop/Ubuntu Zetaris installation and successful JDBC SELECT 1. The project must be feasible in a short hackathon sprint and explain reporting changes with inspectable evidence. Actual project-data ingestion, model capability and Meterless integration remain unverified.

## Decisions

1. Use Python/FastAPI with a small same-origin interface and SQLite application state. A supervised fresh worker isolates blocking JVM/model work from the HTTP event loop. One active investigation is sufficient.
2. Retrieve the three bounded source tables through the exact Zetaris JDBC driver, then calculate using a deterministic Python reference. Move work to SQL only after feature/parity checks. Treat setup SQL as operator provisioning outside the model's runtime capabilities.
3. Implement an explicit finite action loop with strict schemas and fixed tool budgets. Do not add a multi-agent framework, free-form code execution or model-generated SQL.
4. Use actual Meterless H-MEM reference code through a pinned TypeScript helper. Apply OS scope locks across run and outbox helpers. Disclose prototype persistence/mock embedding limits.
5. Keep model inference independent. First verify an available existing Ollama model; allow Meterless Runtime only after real endpoint/authentication/capability checks. H-MEM integration and Meterless Runtime inference are different claims.
6. Preserve reporting and memory observation cutoffs separately. Store current numeric facts only from the selected reporting snapshot; prior approved notes are historical context.
7. Keep current calculations, candidate interpretations and human dispositions separate. The only source-write path is a later deliberately designed operator workflow, outside this prototype.

## Alternatives considered

| Alternative | When preferable | Why deferred here |
|---|---|---|
| Full React application plus separate worker/queue services | Several developers, richer UI, concurrent deployments | Adds build/deployment surfaces before source access and investigations are proven. |
| Entirely TypeScript application | Team strongly prefers Node and a verified JDBC bridge exists | The user's successful bridge and existing analytical workflow are Python-based. |
| Pure Python H-MEM implementation | Language bridge proves untenable and time permits conformance work | Risks claiming compatibility without the actual reference/conformance evidence. |
| Meterless Runtime as sole inference route | Suitable hardware/access and actual model tests pass | Availability has not been demonstrated on the user's setup. |
| Immediate SQL-heavy USL/data-mart architecture | Source onboarding and required Lightning features are already verified | Unnecessary dependency for six facilities and 144 expected facility-months. |

## Consequences

The first build requires Python, Java and Node. It remains a local prototype with one investigation slot, not a multi-user health platform. A proprietary driver stays outside Git. The instance-specific source onboarding recipe is a first implementation decision, not fabricated architecture SQL. Deployment beyond localhost requires explicit authentication, HTTPS, operational controls and separately approved data governance.
