# Offline evidence briefcase — first offline-read slice

AfyaEvidence can run its synthetic evidence calculations and scripted-agent
evaluations locally, and can use an installed Ollama model and the pinned
H-MEM reference without a cloud service. That is **local operation**. It
is not proof that the current authenticated browser can process new live
source data or submit reviews while disconnected.

The first offline capability added on this branch is a **self-contained,
read-only HTML evidence briefcase**. A reviewer can open the exported page
later without internet access, Keycloak, Zetaris, Ollama, JavaScript or a
running AfyaEvidence server. This is an offline copy of *previously prepared
synthetic evidence*, not an offline assistant or a synchronisation queue.

## What is included

- A validated synthetic **fixture/scripted** investigation summary, numerical
  statements cross-checked against deterministic metric facts, and referenced
  evidence identifiers.
- Source receipt SHA-256 and immutable snapshot ID for provenance comparison.
- Explicit limitations, suggested next checks and a clear human-review boundary.
- One local HTML file, with embedded CSS, no scripts, no remote resources, no
  form controls, no network calls and a restrictive Content Security Policy.
- HTML escaping of supplied brief text and refusal to overwrite existing output.

The original receipt remains unchanged and contains the full synthetic
evidence bundle. The portable briefcase intentionally **does not embed raw
source records**, private memory, user identities, bearer tokens, passwords,
SQLite reviews or source connection details. A receipt hash is not a
cryptographic signature or proof of source authenticity.

## Build an offline demonstration

From a WSL checkout of `work/keycloak-live-acceptance`, with Python 3.12+:

```bash
cd "$HOME/afyaevidence-keycloak-live"
source "$HOME/.venvs/afyaevidence-identity/bin/activate"
export PYTHONPATH="$PWD/src"

python scripts/run_agent.py \\
  --data-mode fixture \\
  --snapshot data/synthetic/fx_32e8b610 \\
  --model-provider scripted \\
  --memory disabled_fixture \\
  --output runtime/offline-demo-receipt.json

python scripts/export_offline_briefcase.py \\
  --receipt runtime/offline-demo-receipt.json \\
  --output runtime/offline-demo-briefcase.html
```

Both commands refuse an existing output path. Choose a new timestamped filename
if you have already produced the example files. Do not remove an old receipt
to repeat the test.

Open `runtime/offline-demo-briefcase.html` in a browser. Disconnect the
network (or disable networking) and reopen that *same file*. The page should
still show the synthetic interpretation, exact numerical statements,
provenance and the review-required warning. This is a local acceptance test;
until an operator performs it, a browser offline-reopen PASS is **not claimed**.

## Run the tests

```bash
python -m unittest discover -s tests -p 'test_offline_briefcase.py' -v
python scripts/audit_project_completeness.py
```

Regression tests cover HTML escaping, rejection of live modes, exclusion of
unrelated evidence references, original-receipt preservation and refusal
to overwrite the output.

## Deliberate limitations and next slice

**Supported:** read-only, disconnected access to a previously prepared
synthetic report. The separate [v2 package guide](OFFLINE_EVIDENCE_PACKAGES_V2.md)
adds a ZIP with SHA-256 file checks, an explicit review-by time and a
restricted evidence extract; it does not add offline authenticated review.

**Not supported by this slice:** offline Keycloak login or revocation checks,
offline approval/rejection, real patient or live district data export,
background sync, downloading fresh Zetaris evidence, real Ollama inference
without its running local service, conflict resolution or a persistent
offline-capable browser application.

Future offline-first work should require an approved evidence package format,
signed provenance and schema validation, a local authorised reviewer
capability with expiry, browser storage isolation, encrypted at-rest caching,
explicit append-only offline action queue, conflict-safe one-time
synchronisation and exhaustive logout/revocation/outage tests. Do **not**
turn on offline review submissions without those controls.

## Competition demonstration

The strongest truthful demonstration is to show: (1) evidence collection
and agent preparation while services are available; (2) the exported
briefcase; (3) the internet and services disconnected; (4) the same
evidence brief still opening; and (5) review controls disabled until a
verified online session returns.

This demonstrates usefulness in low-connectivity settings without claiming
an autonomous disease surveillance or clinical decision system.

**Release decision:** The standalone briefcase is a synthetic technical
demonstration. OpenJDK CVEs, independent security review and production
deployment acceptance remain blocked.
