# CircleCI Free — synthetic AfyaEvidence verification

CircleCI provides an independent hosted CI option while GitHub Actions is
unavailable due to the account-level billing restriction. Source control and
review remain on GitHub. A CircleCI project connection requires the operator
to approve access to the repository; no connection is established by these
commits alone.

## Project setup from CircleCI's configuration chooser

Choose **Fastest: Use the `.circleci/config.yml` in my repo**. Select
`buriro-ezekia/afyaevidence`, then **Select a branch with config.yml** and
choose `work/keycloak-live-acceptance`. This is the current draft
integration branch containing the new CircleCI configuration. Then select
**Set Up Project**. Do not choose a generic starter template or automatically
commit a new CI pipeline branch.

The configuration commits only synthetic CI checks. It does not include
private account credentials, real district or patient data, private
Keycloak signing secrets, billing details or live Zetaris access. It does
not use GitHub Actions runners.

## Pipeline contract

`.circleci/config.yml` uses CircleCI configuration version 2.1 with a
Python matrix covering **3.12, 3.13 and 3.14**. Each job uses an
appropriate `cimg/python:<version>-node` convenience image and
asserts **Node.js major 24**, required for the pinned H-MEM reference.
If the selected image ships a different Node major, the preflight
deliberately fails rather than producing misleading H-MEM regressions.
This condition will require an approved image/toolchain correction.

The job installs the optional identity test dependencies, runs
`pip check`, executes
`python scripts/verify_identity_worker.py --fixtures` and checks source
and documentation completeness. The full suite should include the current
locally reported **319 tests**, plus deterministic fixture, H-MEM,
package-isolation and offline trust tests. The exact hosted result and
test counts may differ if code changes before that run.

The config does not upload the entire generated `runtime/` directory
as CI artefacts, because those files are ephemeral verification output.
Console logs remain available in CircleCI. No production approval or
deployment job is defined.

## Evidence and limitations

The operator must inspect each matrix job in CircleCI for its actual
image, Python and Node versions, command results and step failures.
A CircleCI configuration commit is **not** a hosted CI PASS.
Provider registration, project permissions and spending limits must be
confirmed by the operator. Use the free plan only; no billing method
is required for this proposed workflow unless CircleCI's current
onboarding specifies otherwise.

A passing synthetic CircleCI matrix would provide independent hosted
regression evidence, not an independent security assessment or a
substitute for live integration tests. Keycloak CVE-2026-91403 and
CVE-2026-91415, publisher trust governance, dedicated deployment
controls and production release remain unresolved.

## First observed hosted acceptance — 25 October 2026

The operator shared CircleCI pipeline **#1** workflow `synthetic-ci`,
commit `391237a` and branch `work/keycloak-live-acceptance` marked
**Success**. All three Python matrix jobs 3.12, 3.13 and 3.14 were
green (workflow duration 1m 20s). This proves an independent hosted
run without GitHub Actions. The screenshot does not show per-step
unittest counts, so the 319-test local baseline remains separate.
The latest GitHub branch head should be tested again after new commits.
