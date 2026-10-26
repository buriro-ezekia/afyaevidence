# AfyaEvidence — hackathon Phase 1 submission freeze

**Freeze prepared:** 26 October 2026. **Submission deadline:** 27
October 2026 at 23:45 UTC (28 October at 02:45 EAT), as stated
in the organiser's email. This is a **source/evidence freeze**, not a
production or clinical deployment clearance.

## Frozen source identity

- Repository: `buriro-ezekia/afyaevidence`
- Branch: `work/keycloak-live-acceptance` (draft PR #4, intentionally
  unmerged)
- **Frozen candidate source commit:**
  `80fbb9fd52c2ecc0b3f987e476e3908c6fbc4a71`
- Source: https://github.com/buriro-ezekia/afyaevidence/tree/80fbb9fd52c2ecc0b3f987e476e3908c6fbc4a71
- Frozen revision includes the hackathon demonstration witness tool,
  the bounded agent, offline packages and CI setup. New freeze-audit
  helper commits follow the frozen source snapshot; do not call those
  the already-tested candidate.
- Original accepted reviewer decisions, disposable acceptance state,
  GitHub PRs and Keycloak realm/volumes remain untouched.

The **319-test local PASS** and **CircleCI pipeline #1 PASS**
were separately operator-reported. Do not assert their commit SHA
matched the frozen revision without matching runner metadata.
CircleCI #1 visibly ran commit `391237a`, an **earlier** revision.
Python 3.12/3.13/3.14 matrix jobs were green on that revision.
A new CircleCI run explicitly checking the frozen commit is still
needed for commit-matched hosted acceptance.

## Immutable evidence to preserve locally

| Evidence | Reference |
| --- | --- |
| Successful integrated Zetaris/Ollama/H-MEM receipt | `runtime/hackathon-integrated-20261025T175903Z.json` |
| Full integrated receipt SHA-256 | `3befe3839b2988398a30ffc786d8f4f4bc6a77274dc9be637aa6eb2e7a813af1` |
| Credential-free demo witness | `runtime/hackathon-witness-20261025.json` |
| Earlier fixture receipt | `runtime/offline-demo-receipt.json` |
| Local verification output | `runtime/identity-verification-20261025T170250936725Z` |
| Historical runtime wheel SHA-256 | `fd079677a16852b86b0fce69bc7baab7e27b6130c71ffe4af07e7941dccd9076` |
| CircleCI first hosted three-Python success | Pipeline #1, commit `391237a` (screenshots) |

The integrated operator output showed `LIVE_ZETARIS=PASS`,
`LIVE_MODEL=PASS`, `LIVE_HMEM=PASS`, two model calls,
five tool calls, no repairs,
`EXPLANATION=reporting_artefact_supported`,
`REVIEW_STATUS=awaiting_human_review`,
`RECALLED_NOTES=0` and `MEMORY_PENDING_SYNC=0`.
No historical H-MEM note shaped this observed explanation.
The stored witness is not an independent network attestation.

Do **not** copy raw source receipts, JDBC credentials, private
signing keys, review databases or token-bearing logs into Git or
public submission attachments.

## Run the Phase 1 freeze audit

The new auditor reads local evidence and Git metadata only.
It checks that the current checkout descends from the source
revision, tracked files have no uncommitted changes, and the
witness's integrated receipt SHA-256 matches both the local
receipt bytes and the expected previously reported hash.
It writes a new allowlisted JSON report under ignored `runtime/`.

Terminal 2:

```bash
cd "$HOME/afyaevidence-keycloak-live"
git fetch origin
git switch --detach origin/work/keycloak-live-acceptance
source "$HOME/.venvs/afyaevidence-identity/bin/activate"
export PYTHONPATH="$PWD/src"

python -m py_compile scripts/audit_submission_freeze.py tests/test_submission_freeze.py
python -m unittest discover -s tests -p 'test_submission_freeze.py' -v

python scripts/audit_submission_freeze.py \\
  --witness runtime/hackathon-witness-20261025.json \\
  --integrated-receipt runtime/hackathon-integrated-20261025T175903Z.json \\
  --output runtime/hackathon-phase1-freeze-20261026.json
```

Choose a new output filename if that one already exists. Never
delete or replace previous receipt and verification files.
A passing audit prints `SUBMISSION_FREEZE=PASS`,
`FROZEN_SOURCE_COMMIT=80fbb9fd...`,
`SOURCE_WORKTREE=CLEAN_TRACKED_FILES` and
`CIRCLECI_FROZEN_COMMIT=NOT_VERIFIED` until corresponding hosted
evidence becomes available.

Run the **full suite** from the new checkout using Node 24:
```bash
source "$HOME/.nvm/nvm.sh"
nvm use 24
python scripts/verify_identity_worker.py --fixtures
python -m pip check
```

These checks may increase the test count beyond the historical 319,
because the new freeze auditor adds four tests. Only actual output
can establish the updated PASS and verification directory.

## Diagnostic follow-up — 26 October 2026

The first operator attempt returned
`SUBMISSION_FREEZE=BLOCKED_EVIDENCE_OR_WORKTREE`, without a reason
because the initial audit collapsed all failures. The updated script
now emits a constrained `SUBMISSION_FREEZE_REASON` code. It does not
disclose private receipt contents, Git errors, passwords or tokens,
and the source hash and review safeguards remain unchanged.

Use a **new** report destination for each attempt:

```bash
cd "$HOME/afyaevidence-keycloak-live"
git fetch origin
git switch --detach origin/work/keycloak-live-acceptance
source "$HOME/.venvs/afyaevidence-identity/bin/activate"
export PYTHONPATH="$PWD/src"

python -m py_compile scripts/audit_submission_freeze.py tests/test_submission_freeze.py
python -m unittest discover -s tests -p 'test_submission_freeze.py' -v

python scripts/audit_submission_freeze.py \\
  --witness runtime/hackathon-witness-20261025.json \\
  --integrated-receipt runtime/hackathon-integrated-20261025T175903Z.json \\
  --output runtime/hackathon-phase1-freeze-diagnostic-20261026.json
```

If `SUBMISSION_FREEZE_REASON=tracked_worktree_not_clean`, inspect
`git status --short`; do not discard changes or force-reset the worktree.
If `output_already_exists`, choose a new report name. If a witness or
receipt mismatch is reported, preserve both files and use
`sha256sum` only to compare digests; never reconstruct or alter a
historical successful receipt to force the audit to pass.
A `frozen_commit_not_on_checkout` result requires examining the
current checkout and Git ancestry, not rewriting the frozen source
identity. The audit's `CIRCLECI_FROZEN_COMMIT=NOT_VERIFIED` status
continues to require a separate commit-matched hosted CircleCI run.

## Git commit SHA validation correction — 26 October 2026

The operator's six freeze tests passed, but the first detailed freeze run
reported `SUBMISSION_FREEZE_REASON=invalid_head_sha`. The original
script accidentally validated `git rev-parse HEAD` against the
**64-character SHA-256 receipt digest** pattern. This repository uses
standard **40-character Git SHA-1 commit IDs**, so the check always
blocked an otherwise valid HEAD. The source and integrated-receipt
hashes use distinct formats and must never be conflated.

The corrected verifier accepts full Git object identifiers of 40 or 64
lowercase hexadecimal characters, rejects abbreviated/non-hex IDs,
and retains the 64-character requirement for *receipt* digests.
The pinned source revision, Git ancestry and clean-worktree checks
remain unchanged. A new regression test covers both full Git formats
and invalid examples. No Git history, evidence receipt, review event
or security boundary was rewritten.

Repeat `py_compile` and the now **seven** focused freeze tests,
then rerun with a **new** output name. This commit fixes the diagnosed
`invalid_head_sha` check; other audit gates remain real and may still
need independent investigation.

## Phase 1 acceptance evidence — 26 October 2026

The operator's successful read-only freeze audit returned:

```text
SUBMISSION_FREEZE=PASS
FROZEN_SOURCE_COMMIT=80fbb9fd52c2ecc0b3f987e476e3908c6fbc4a71
AUDITOR_CHECKOUT_HEAD=d3941a519a7ca8430f3d13629375c8712c7b2954
INTEGRATED_RECEIPT_SHA256=3befe3839b2988398a30ffc786d8f4f4bc6a77274dc9be637aa6eb2e7a813af1
CIRCLECI_FROZEN_COMMIT=NOT_VERIFIED
SOURCE_WORKTREE=CLEAN_TRACKED_FILES
SUBMISSION_STATUS=DRAFT
PRODUCTION_RELEASE=BLOCKED
FREEZE_OUTPUT=runtime/hackathon-phase1-freeze-sha-fix-20261026.json
```

Updated local fixture regression **335 tests PASS (71.306 seconds)**,
16 evaluation scenarios, 15 deterministic snapshots, 32 scripted
agent runs in standard/cpu profiles, H-MEM reference checks PASS,
isolated runtime wheel PASS and `pip check` no broken requirements.
Local verification directory:
`runtime/identity-verification-20261026T061827628070Z`.
Wheel digest:
`3b85c765183d3024a8e7c51e2c53f49b673b3a0284430dc171624d168ab4b0ab`.

CircleCI **pipeline #26, workflow `synthetic-ci`, commit `d3941a5`,
branch `work/keycloak-live-acceptance`: SUCCESS. All three
`synthetic-verification` Python 3.12, 3.13 and 3.14 jobs were
green in the operator's screenshot (pipeline completed in ~1m28s).
This independently hosts the fixture-only suite at the **auditor
checkout** revision; the original pinned source revision is its
ancestor but was not itself the CircleCI pipeline's checkout.

The latest suite explicitly reported `LIVE_MODEL=NOT_RUN`,
`LIVE_ZETARIS=NOT_RUN`, `LIVE_HMEM=NOT_RUN`.
The separately witnessed earlier combined integration is the evidence
for actual sponsor calls. Do not describe the fixture matrix as a
live-services test, a network attestation, or a clinical/production
release approval.

**Phase 1 source/evidence freeze accepted for hackathon readiness.**
This documentation update is a later commit and does not retroactively
change the previously tested source revision.
The HackOS application is still draft. Production release remains blocked.

## Exit criteria

- [x] Frozen source commit identified.
- [x] Prior integrated receipt/witness exact paths and hash recorded.
- [x] Historical local and CircleCI checks clearly documented.
- [x] Freeze audit PASS against checkout `d3941a5` (operator output, 26 October).
- [x] Full suite PASS: 335 tests in 71.306 seconds (operator output, 26 October).
- [x] CircleCI pipeline #26 PASS on auditor checkout `d3941a5` across Python 3.12/3.13/3.14; exact earlier frozen source commit `80fbb9f` was **not** separately run by this pipeline.
- [ ] Final recorded demo, description and required HackOS submission.

**Judges:** Use the fixed source link above, not an assumed
default-branch HEAD. This milestone is an **experimental synthetic
health reporting investigation**, not live clinical decision-making.
Candidate Keycloak image retains critical/high OpenJDK findings,
and `PRODUCTION_RELEASE=BLOCKED`.
