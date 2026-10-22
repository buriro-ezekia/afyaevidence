# AfyaEvidence implementation instructions

This repository contains the architecture, source-access verifiers, synthetic suite and bounded runtime snapshot/analysis package. Read README.md, docs/FIRST_DATA_ACCESS.md and docs/ARCHITECTURE.md, then implement the ordered issues in docs/IMPLEMENTATION.md. Do not claim sponsor integration, the agent application or deployment is complete until the relevant checks actually run.

- Build the scoped synthetic malaria reporting investigation workflow. Keep diagnosis, treatment, outbreak declaration, real patient data, forecasting and source edits outside this increment.
- Use the user's exact Zetaris JAR and `com.zetaris.lightning.jdbc.LightningDriver`; execute one Lightning statement per call. Never start Spark or use a Hive/Spark substitute driver.
- Verify project-data loading and query semantics on the actual instance before coding elaborate SQL. Separate setup/provisioning from the agent's SELECT-only runtime. Inspect existing objects and avoid destructive changes.
- Keep calculations, revision resolution, denominators and evidence IDs deterministic. Models select allowed analyses and propose interpretations; they do not supply trusted arithmetic or approval decisions.
- Preserve immutable snapshots, report cutoffs, memory cutoffs and explicit missing/invalid states. Do not silently select older valid versions when the latest observed version is invalid or withdrawn.
- Keep fixture/live data, scripted/real model and actual/disabled memory modes distinct through UI, tests and exports. An unavailable or skipped check is not PASS. Never hide a live failure with fixture replay.
- Pin actual Meterless H-MEM reference code, record attribution and disclose prototype/mock-embedding limitations. Apply a cross-process scope lock and test outbox/restart behaviour. Treat memory as historical context, not current measurement.
- Keep scenario answer keys outside app packages, data mounts, tools and prompts. The agent gets no filesystem/shell/unrestricted network tool.
- Do not commit credentials, JARs, local databases, node_modules, runtime state or real health records. Use a gitignored local environment file and the supplied authorised JAR separately.
- Human review requires its own browser capability, idempotency key and expected revision. Never add it to the agent's tool registry or let it alter source records.
- Run checks appropriate to each slice and report actual results and blocked dependencies. Preserve meaningful failed live/evaluation evidence without secrets.
- Reuse existing project code only after reviewing licence/attribution and tracking pre-existing work for the event rules. No prior repository status implies this new project is ready.
