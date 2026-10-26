# Open Agent Hackathon 2026 — AfyaEvidence submission readiness

**Source:** Hackathon Team email received 25 October 2026,
subject *Halfway: where your build should be, plus a $100 LinkedIn
bonus*. The email states 22–27 October, online; submission closes
**Tuesday 27 October 2026 at 23:45 UTC** (Wednesday 28 October,
**02:45 East Africa Time**). Check the official HackOS submission
form for the final requirements before publishing.

The email requests an end-to-end working agent, realistic messy-input
testing, both **Zetaris and Meterless connected within the build**,
and a deliberately reduced demo scope.

## What current evidence establishes

- Local full regression: **319 tests passed** (operator report,
  25 October), including 15 reproducible synthetic snapshots,
  16 evaluation cases and 32 scripted fixture runs.
- Independent hosted CircleCI pipeline **#1**, workflow
  `synthetic-ci`, branch `work/keycloak-live-acceptance`,
  commit `391237a`: all three Python matrix jobs 3.12/3.13/3.14
  green in the operator screenshot. The CircleCI build is independent
  of GitHub Actions billing. Exact step logs were not supplied.
- Zetaris JDBC source retrieval and the pinned Meterless H-MEM
  reference were individually validated earlier, but the latest
  319-test and CircleCI runs were fixture-only. **They are not
  proof that the current combined live Zetaris + Ollama + Meterless
  agent workflow succeeded.**
- Keycloak's candidate image still reports
  `CVE-2026-91403` and `CVE-2026-91415`.
  Production release remains **BLOCKED**. Do not present this demo
  as clinical decision support, deployed public-health surveillance
  or a production-cleared authentication system.

## The demo we should actually show

**Input:** A fictional district, a comparison month, a target month
and a fixed observation cutoff.

**Agent:** Reads previously staged synthetic *aggregate malaria
reporting* through Zetaris JDBC, uses the actual local Ollama model,
retrieves bounded historical review context through the actual pinned
Meterless H-MEM reference, runs host-controlled reporting-quality
and monthly-comparison tools, and proposes evidence-cited findings.

**Output:** A run receipt and a candidate brief marked
`ready_for_review` / `awaiting_human_review`. No outbreak
declaration, no source edits and no automatic review approval.

**Messy cases to highlight:** old-versus-current report versions;
duplicate/revised submissions; differences between raw and accepted
canonical totals; missing or withdrawn reports. The synthetic
evaluation already tests these categories, but use only results
actually observed in the selected run.

## First run a safe operator preflight

Terminal 1 is not needed for scripted verification, but **actual
Zetaris, local Ollama and pinned H-MEM services must be reachable**
to establish integrated success. Keep credentials in your existing
private host environment, not shell history or shared logs.

```bash
cd "$HOME/afyaevidence-keycloak-live"
source "$HOME/.nvm/nvm.sh"
nvm use 24
source "$HOME/.venvs/afyaevidence-identity/bin/activate"
export PYTHONPATH="$PWD/src"

python -m py_compile scripts/check_hackathon_demo.py tests/test_hackathon_demo.py
python -m unittest discover -s tests -p 'test_hackathon_demo.py' -v
python scripts/verify_hmem.py --doctor

python scripts/check_hackathon_demo.py \\
  --fixture-receipt runtime/offline-demo-receipt.json
```

The last command intentionally returns **exit code 3** and prints
`HACKATHON_DEMO_GATE=INCOMPLETE` when no integrated receipt is
supplied. That is an honest missing-evidence flag, not a failed
synthetic investigation.

## Actual Zetaris + Ollama + H-MEM demonstration

The model endpoint recorded in older documentation was a temporary
Windows/WSL interface address; it must be checked locally again,
rather than assumed unchanged. The actual model names available
also depend on the running Ollama service. Use your own previously
verified local JDBC credentials and driver; never paste passwords,
admin tokens, private keys or full live receipts into a public post.

Start with:
```bash
python scripts/verify_model.py --endpoint http://172.22.160.1:11434 --list-models
```

If this endpoint is no longer valid after WSL restart, substitute the
**currently verified local Ollama origin**. Do not silently switch to
the scripted provider.

When the local model probe passes, run a new bounded CPU-profile
receipt. The example below uses previously documented synthetic
Zetaris staging and an already provisioned JDBC driver:

```bash
source "$HOME/zetaris-setup/zetaris-platform/.venv-jdbc/bin/activate"
export PYTHONPATH="$PWD/src"
source "$HOME/.nvm/nvm.sh"
nvm use 24

python scripts/run_agent.py \\
  --data-mode zetaris \\
  --snapshot data/synthetic/fx_32e8b610 \\
  --database AFYAEVIDENCE_REVISION \\
  --jar "$HOME/zetaris-setup/zetaris-platform/jdbc/ndp-jdbc-driver-2.4.3.1-7eff043-driver.jar" \\
  --url jdbc:zetaris:lightning@localhost:10000 \\
  --model-provider ollama \\
  --execution-profile cpu \\
  --endpoint http://172.22.160.1:11434 \\
  --model qwen2.5:1.5b \\
  --model-timeout 300 \\
  --memory hmem_reference \\
  --bridge-dir bridges/hmem \\
  --output "runtime/hackathon-live-$(date -u +%Y%m%dT%H%M%SZ).json"
```

**Important:** The identity virtual environment and JDBC environment
are distinct. Reuse the existing tested JDBC Python environment for
this command, and check that Node 24 is active. When Zetaris needs a
password the CLI prompts privately on a real terminal, unless it is
already provided through private environment configuration.
Use only fictional/synthetic data sources. If the driver path,
staging table, source connection, model or bridge differs, do
not invent a replacement or claim PASS.

The operator must observe `AGENT_EXECUTION=PASS`,
`EXECUTION_STATUS=ready_for_review`, `LIVE_ZETARIS=PASS`,
`LIVE_MODEL=PASS` and `REVIEW_STATUS=awaiting_human_review`.
`LIVE_HMEM=PASS` is printed only when the run actually reads
historical context; a first empty scope can legitimately have
zero recalled notes. Record that distinction. If the live run
fails, report the stage/failure reason rather than substituting
fixture success.

Finally, use both receipt paths:

```bash
python scripts/check_hackathon_demo.py \\
  --fixture-receipt runtime/offline-demo-receipt.json \\
  --integrated-receipt "runtime/<ACTUAL-NEW-LIVE-RECEIPT>.json"
```

This verifier is **read-only**. It validates the declared receipt
modes, evidence and human-review boundary. Local JSON can be forged,
so `HACKATHON_INTEGRATED_RECEIPT=PASS` is not an independent
service attestation; keep terminal logs or a recorded terminal
demonstration showing actual service interaction.

## Current combined integration milestone — 25 October 2026

The operator has now run an actual combined investigation with:
`DATA_MODE=zetaris`, `MODEL_MODE=ollama` and
`MEMORY_MODE=hmem_reference`. The agent reported
`AGENT_EXECUTION=PASS`, `EXECUTION_STATUS=ready_for_review`,
`LIVE_ZETARIS=PASS`, `LIVE_MODEL=PASS`, `LIVE_HMEM=PASS`,
two model calls, five tool calls, zero repairs, and
`EXPLANATION=reporting_artefact_supported`. The candidate stayed
`awaiting_human_review`. Exactly **zero** historical notes were
recalled and no memory sync remained pending. It would be incorrect
to say historical H-MEM notes influenced that result.

The operator's corrected read-only gate returned
`HACKATHON_INTEGRATED_RECEIPT=PASS` and
`HACKATHON_DEMO_GATE=READY_FOR_OPERATOR_WITNESS` using
`runtime/hackathon-integrated-20261025T175903Z.json`.
This is verified **operator receipt evidence**; it does not itself
cryptographically attest the external services. The primary remaining
demonstration task is showing a coherent, source-backed workflow
without revealing credentials.

### Prepare the minimal presentation witness

A new read-only helper selects only known non-sensitive receipt fields,
writes their SHA-256 digests and records human-review and synthetic
scope limitations. It **does not embed full receipts**, raw metrics,
private model prompts, JDBC strings, credentials or source records.

```bash
cd "$HOME/afyaevidence-keycloak-live"
source "$HOME/.venvs/afyaevidence-identity/bin/activate"
export PYTHONPATH="$PWD/src"

python -m py_compile scripts/prepare_hackathon_witness.py tests/test_hackathon_witness.py
python -m unittest discover -s tests -p 'test_hackathon_witness.py' -v

python scripts/prepare_hackathon_witness.py \\
  --fixture-receipt runtime/offline-demo-receipt.json \\
  --integrated-receipt runtime/hackathon-integrated-20261025T175903Z.json \\
  --out runtime/hackathon-witness-20261025.json
```

The witness must report `HACKATHON_WITNESS=PASS` and
`HACKATHON_SERVICE_ATTESTATION=NOT_INDEPENDENTLY_VERIFIED`.
A witness is an aid to demonstration, **not** independent source
authentication or a successful public submission. Keep the full
receipt private. For video, show the terminal execution summary,
the high-level workflow diagram, human-review banner and the
read-only offline briefcase; do not show terminal history or type
private JDBC passwords into a recorded screen.

## Operator witness acceptance — 25 October 2026

The operator generated the redacted read-only witness successfully:

```text
HACKATHON_WITNESS=PASS
HACKATHON_INTEGRATED_RECEIPT_SHA256=3befe3839b2988398a30ffc786d8f4f4bc6a77274dc9be637aa6eb2e7a813af1
HACKATHON_EXPLANATION=reporting_artefact_supported
HACKATHON_RECALLED_CONTEXT_COUNT=0
HACKATHON_SERVICE_ATTESTATION=NOT_INDEPENDENTLY_VERIFIED
HACKATHON_REVIEW_STATUS=awaiting_human_review
PRODUCTION_RELEASE=BLOCKED
HACKATHON_WITNESS_FILE=runtime/hackathon-witness-20261025.json
```

This closes the **local witness-generation gate**. Its receipt digest
can be used to compare with the preserved integrated JSON receipt, but
is not a network-service attestation or publisher signature. The
witness excludes underlying sensitive receipt contents and demonstrates
the continuing human-review boundary. The operator has not yet
provided a recorded walkthrough, final submission acknowledgement or
independent security approval. The separate focused witness-test
summary was not included in this reported output.

## Phase 1 frozen submission revision

The [freeze and evidence record](HACKATHON_PHASE1_FREEZE.md) pins
the source version to commit `80fbb9fd52c2ecc0b3f987e476e3908c6fbc4a71`
and the integrated receipt digest to
`3befe3839b2988398a30ffc786d8f4f4bc6a77274dc9be637aa6eb2e7a813af1`.
The evidence-freeze audit is separate from production security and
the historical CircleCI run, which executed an earlier commit.
Do not claim the new freeze audit or commit-matched CI passed until
operator execution confirms it.

## Submission and optional LinkedIn bonus

Only include what was actually demonstrated. A credible demo can
consist of: input scope → real tool calls → source-linked numeric
evidence → bounded agent explanation → human-review gate → offline
read-only evidence briefcase. The signed offline v2–v4 packages can
be shown as an optional low-connectivity extension, not as a
substitute for the sponsor integrations.

The email additionally invites a LinkedIn progress post tagging
**@Zetaris** and **@GenAI.works** with
**#OpenAgentHackathon**. It says to reply to the same email with
the post URL for a chance at one of ten $100 awards. The email does
not establish a guaranteed prize or specify a separate bonus
submission deadline. Do not include sensitive source or credentials.

## Submission acceptance summary

| Gate | Status before fresh actual-service run |
| --- | --- |
| Synthetic agent and evaluation | PASS (operator report) |
| Independent hosted CI | PASS for CircleCI #1 commit 391237a (screenshot) |
| Current actual combined sponsor integrations | NOT_VERIFIED |
| Human review before approval | PASS in synthetic workflow |
| Offline read-only briefcase | PASS (local demonstration) |
| Keycloak release security | BLOCKED |
| Production/clinical approval | BLOCKED |
