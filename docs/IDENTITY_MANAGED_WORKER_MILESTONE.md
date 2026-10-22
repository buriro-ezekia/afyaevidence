# Identity and managed-worker milestone — implementation contract

Status: **design and acceptance plan only**. No production authentication or
cgroup-managed worker is implemented by this document. Based on PR #2 at
`cfb05bb28395bfc3ae1e87dbf52be46f99991396`. Keep PRs #1 and #2 unmerged.

## Security review gate

A dedicated `@codex security review` was requested on PR #2. Record the
actual review result, address each finding with a regression test, and
re-request review after fixes. A request is not a completed security review.

## Reviewer identities

Use an established OIDC identity provider for authenticated individuals.
Validate issuer, audience, signature via trusted JWKS, expiry, not-before,
subject, and an allowlisted authorised reviewer role. Do not trust unverified
JWT payloads or arbitrary request headers. Separate `viewer`, `reviewer`,
and `administrator` permissions. Bind each immutable review event to the
verified issuer+subject, not `local_operator`. Reject revoked, expired,
wrong-audience and unauthorised tokens. Fail closed if identity verification
is unavailable. Require HTTPS outside loopback and ensure CSRF protection
for cookie-backed sessions; never expose access tokens in URLs or logs.

The existing local bearer-token interface must remain a development-only
path and must not silently grant production reviewer permissions.
Provide migration preserving old review rows and marking legacy
`local_operator` identities as unverified. Never backfill a guessed person.

## Managed worker

Use a Linux systemd service with `Delegate=` and a dedicated cgroup v2
scope for each agent process group, or an equivalent supported container
runtime with per-job cgroup ownership. Do not rely solely on process-group
signals. Enforce CPU/memory/pid/time limits, non-root identity, bounded
concurrency, and explicit cancellation. Persist job intent, start, PID/cgroup
identity, receipt checksum and final outcome transactionally.

After restart, reconcile existing cgroups, receipts and job events before
admitting new work. Incomplete jobs become `needs_operator_reconciliation`;
never replay model or source calls automatically. Confirm the child and all
descendants have exited before releasing ownership. Audit operator recovery
actions with verified identity and reasons.

## Acceptance matrix

| Gate | Minimum evidence |
| --- | --- |
| OIDC identity | Good token, bad issuer/audience/signature, expired, revoked, role denial |
| Review immutability | Concurrent reviewers, duplicate keys, migration preserving revision 1 |
| API hardening | Origin, CSRF as applicable, request caps, error sanitisation, no token logging |
| Worker containment | SIGTERM, SIGKILL, orphan grandchild, timeout, OOM and restart |
| Reconciliation | Missing/corrupt receipt, cgroup still alive, duplicate job claim |
| Deployment | TLS, secrets, least privilege, backups/restore, monitoring, rollback |
| Live acceptance | Synthetic source only, no clinical action, review-only candidate |

Run the existing 178-test baseline plus new integration tests on the
target Ubuntu/systemd environment. If WSL does not expose the required
cgroup delegation, record a blocked integration gate rather than claiming
cgroup containment. Hosted GitHub Actions remains separate from local
acceptance and may be administratively blocked.

Do not deploy or merge until security review, local integration,
operator-run browser checks and deployment smoke have passed.
