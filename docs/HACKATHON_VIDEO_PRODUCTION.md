# AfyaEvidence — four-minute hackathon demonstration production pack

**Status:** Production plan and narration ready. **Actual screen recording, editing, publicly accessible video and HackOS submission are not yet evidenced.**

Target: **3 minutes 20–40 seconds**, maximum **4 minutes**. Format: 1920×1080, 16:9, 30 fps, readable UI and terminal fonts. Presented in clear, professional UK English by the Tanzanian male builder, Buriro Chimodoi Ezekia, or with an explicitly labelled synthetic narrator. Do not fabricate voice or likeness.

## Source of truth and proof constraints

- [Candidate source commit](https://github.com/buriro-ezekia/afyaevidence/tree/80fbb9fd52c2ecc0b3f987e476e3908c6fbc4a71); separate checked auditor commit `d3941a5`.
- Operator-reported integrated receipt: `runtime/hackathon-integrated-20261025T175903Z.json`, SHA-256 `3befe3839b2988398a30ffc786d8f4f4bc6a77274dc9be637aa6eb2e7a813af1`.
- The redacted witness `runtime/hackathon-witness-20261025.json` is allowlisted, but not an independent network attestation.
- Local regression: 335 tests PASS; CircleCI #26 at `d3941a5` with Python 3.12–3.14 green. The fixture suite does **not** exercise live sponsors.
- Integrated agent reported `LIVE_ZETARIS=PASS`, `LIVE_MODEL=PASS`, `LIVE_HMEM=PASS`, two model calls, five tool calls, zero repairs, `reporting_artefact_supported`, `awaiting_human_review`. It recalled **zero** prior H-MEM notes.
- Production release **BLOCKED**; no patient records, clinical conclusions, outbreak declaration or autonomous approval.

## Shot list and narration

### Scene 1 — 0:00–0:30: the question (30 seconds)

**Picture:** Plain branded title card, then a simple graph or synthetic records labelled *Fictional dataset*. No realistic hospital footage masquerading as deployment.

**Voice:**

> In malaria reporting, a rise in positive cases can prompt urgent questions. But sometimes a revised report has been counted twice, or more people have been tested. I built AfyaEvidence to help district reviewers investigate changes like these using evidence they can inspect, without allowing an AI model to make public-health decisions for them.

### Scene 2 — 0:30–1:05: architecture and data sources (35 seconds)

**Picture:** Zoomable architecture diagram from `docs/HACKATHON_JUDGES_GUIDE.md`; visually highlight Zetaris, Ollama, Meterless H-MEM, host-controlled calculations and human reviewer. Use actual Zetaris workspace screen only if no secrets appear.

**Voice:**

> The starting point is synthetic aggregate reporting data stored as CSV-backed tables in Zetaris. AfyaEvidence reads them through reviewed JDBC queries. Deterministic Python tools handle report versions, data quality and the arithmetic. A local Ollama model selects from permitted investigation actions. The pinned Meterless H-MEM reference provides scope-controlled historical review context. The model does not control the source database or the approval process.

### Scene 3 — 1:05–2:10: evidence and actual integrated run (65 seconds)

**Picture:** Synthetic scenario `fx_32e8b610`; show 500 tested and 100 positives in the accepted comparison/target periods, then erroneous raw target 600 tested and 120 positives. Show the real **previously captured** integrated operator terminal result (or reproduce only if all services are safely configured). Crop out credentials, private file paths, user names, tokens and source text. Overlay “Operator-reported integrated demo, 25 October 2026”.

**Voice:**

> Here is a fictional reporting-revision example. If the old and replacement facility reports are added together, the target appears to contain six hundred tests and one hundred and twenty positives. But the accepted, version-aware totals are five hundred tests and one hundred positives, unchanged from the comparison month. The agent checks the reporting quality and monthly comparisons rather than inventing its own calculations. In the integrated test, Zetaris retrieval, Ollama reasoning and the H-MEM connection succeeded, with two model calls and five tool calls. No earlier memory notes were recalled during this particular run.

### Scene 4 — 2:10–2:50: explanation and human authority (40 seconds)

**Picture:** Redacted result card using **actual evidence identifiers where safe**; foreground `reporting_artefact_supported`, `ready_for_review` and `awaiting_human_review`. Do not fabricate a source citation ID or show an “Approved” disposition.

**Voice:**

> AfyaEvidence's supported explanation is a reporting artefact: the apparent increase comes from counting an older version alongside its replacement. The brief points the reviewer back to the reporting evidence. It is explicitly marked awaiting human review. That distinction is deliberate. This agent can support an investigation, but it cannot approve its own findings, alter the source records or declare an outbreak.

### Scene 5 — 2:50–3:30: offline evidence and results (40 seconds)

**Picture:** Read-only offline evidence briefcase opened while Chrome DevTools shows “Offline”, if available from the previous locally confirmed demo; then a plain CI results board: “335 local tests; 16 synthetic scenarios; 32 scripted agent executions; CircleCI Python 3.12, 3.13, 3.14 green”. Finish with GitHub repository and “Synthetic prototype — production deployment not approved”.

**Voice:**

> A completed synthetic investigation can also be exported as a read-only evidence briefcase and inspected without an internet connection. Local verification passed three hundred and thirty-five tests, including sixteen synthetic evaluation scenarios and thirty-two scripted agent executions. Three hosted CircleCI jobs also passed. Those automated tests are separate from the earlier live integration, and this remains a prototype, not clinical decision support. My aim is to make unusual reporting changes easier to investigate while keeping decisions with the people responsible.

## Codex hand-off: exact, bounded tasks

**Goal:** Prepare truthful, local demo artefacts and facilitate a safe final capture. Make **no** modifications to protected Keycloak realm, accepted review database, previously saved receipts or signatures.

1. Check branch/revision and current source. Prefer a new demo-only feature branch from `work/keycloak-live-acceptance`, **not** an unreviewed merge into `main`.
2. Confirm the documented scripted fixture CLI flags from `scripts/run_agent.py --help`; do not invent a demo command.
3. Implement `scripts/prepare_demo_assets.py` **only if necessary**: consume allowlisted witness fields, output an original static SVG/HTML card and a source-linked synthetic raw-versus-canonical table with a prominent `SYNTHETIC` label. Never copy full raw agent receipts to web assets; no external calls.
4. Add tests: original witness unchanged, missing/invalid witness blocked, restricted output fields, synthetic labels present, files never overwritten, no credentials.
5. If there is already a read-only briefcase, reuse the validated exporter rather than duplicating its internals.
6. Update this guide with precisely tested setup/capture commands. Run Python syntax checks, focused tests and the existing full synthetic suite in Node 24; report accurate totals and new commit SHA.
7. Optionally prepare text subtitles (SRT) reflecting the narration and shot timing, but do not claim recorded speech exists.
8. Never fabricate a video of terminal commands, a hosted CI result, a Zetaris workspace, a reviewer action or a historical memory recall.

**Completion standard:** Existing proofs remain immutable, new demo artefacts are clearly labelled synthetic, all focused checks pass, and a reviewer can record a credible 3:30 demonstration without showing private material.

## Runway hand-off

Runway can help with **visual polish**, not technical proof. Suggested visual assets:

- **Opening still:** “Professional scientific-data illustration, abstract spreadsheet cells gradually forming a clean bar chart, subtle visual references to East African public health reporting, deep navy and turquoise, minimalist, 16:9, no identifiable people, no logos, no medical patients, no claims of deployment.”
- **Closing still:** “A modern, clean evidence review workspace metaphor: three layered cards labelled DATA, EVIDENCE, HUMAN REVIEW; subtle visual connections; dark professional background; teal and pale blue accents, 16:9, no invented software screenshots.”
- If the workspace supports video generation, animate only these abstract transitions. **Do not generate a fake recording of the real AfyaEvidence agent, Zetaris dashboard or CircleCI.**
- Use original OBS recordings for evidence and operational interactions, with narration spoken by the builder (or clearly labelled computer-generated voice if chosen).

Connected Runway workspace availability is account-dependent. Confirm its active plan/model permissions before commissioning paid video or synthetic speech.

## Final capture and hand-off checklist

- [ ] Record real application/terminal screen segments with no secrets or identifiers.
- [ ] Record narration; confirm all statements match demonstrated scope.
- [ ] Add only non-evidentiary Runway motion graphics if available.
- [ ] Export MP4 H.264/AAC, 1920×1080, 30 fps, total under 4:00.
- [ ] Review all frames for credentials and synthetic-data labels; inspect at normal speed with sound on.
- [ ] Upload to accessible YouTube/Vimeo/Google Drive; verify as a signed-out viewer.
- [ ] Include GitHub solution link and written submission (150–2,000 characters).
- [ ] Obtain explicit HackOS submitted acknowledgement; preserve confirmation.

**Do not treat this production pack as a finished video or a HackOS submission.**
