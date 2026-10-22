# Individual identity and managed workers — implemented, pending live acceptance

## What this slice adds

This is an additive implementation based on the identity milestone at commit
`8c6fb2cacc96cd7bb1cfba127a6cc8d2b54002a3`, whose application baseline is
`cfb05bb28395bfc3ae1e87dbf52be46f99991396`. It does not replace the earlier
loopback review server, its tokens, SQLite database, receipts or supervision code.
The package installer creates a separate local Git worktree and local branch.
It does not commit, push, merge, stash, reset or discard work.

### Identity and authorisation

`identity_auth.py` implements an OIDC-provider **access-token resource server**,
not a complete browser login client. RS256 is fixed by the application. Signature,
issuer, exact audience, access-token type, subject, ID, issued/not-before/expiry
times, short lifetime and roles are checked. Header-supplied key URLs, unsupported
extensions, duplicate JSON keys, non-finite claims and ambiguous key identifiers
are rejected. Trusted operator configuration supplies HTTPS JWKS and introspection
URLs. Redirects and ambient proxies are disabled; reads and timeouts are bounded.

Online introspection is mandatory for every authenticated request: inactive,
revoked, mismatched or unavailable provider responses fail closed. There is no
shared bearer-token fallback. This intentionally trades availability for explicit
revocation enforcement. The provider must return `active`, `iss`, `aud`, `sub`
and `exp` matching the signed access token. Access tokens must have `typ=at+jwt`,
string `aud`, `iat`, `nbf`, `exp`, `jti`, and a list-valued configured roles claim.
Provider adapters using a different contract require explicit tests, not relaxed
validation or unsafe decoding. The provider must restrict reviewer roles to the
intended human accounts; an issuer/subject claim alone is not independent proof
of personhood or identity proofing. Roles are instance-wide for this existing
single-district synthetic application, not multi-tenant district authorisation.

| Role | Read evidence | Submit a review | Reconcile a worker |
|---|---|---|---|
| viewer | Yes | No | No |
| reviewer | Yes | Yes | No |
| administrator | Yes | No unless also reviewer | Yes |

`identity_store.py` adds identity and grant tables to a **backup** of a schema-v2
review database. New review decisions bind issuer and subject to an immutable
actor record and store the verified role snapshot. Legacy `local_operator`
reviews remain unchanged and are displayed as individually unverified. No person
is guessed for an old record. Identity-enabled databases reject new anonymous
review inserts. Original candidate approval remains null; review dispositions do
not approve clinical decisions. SQLite transactions protect concurrent writes and
idempotency binds the run, actor, revision, decision and reason.

### Separate HTTP surface

`identity_review_server.py` binds only `127.0.0.1`, default port 8011. The original
port-8010 development server is unchanged. Host, Origin, JSON content type, body
framing and size are validated. There is no CORS or cookie session. Scripts/styles
are same-origin assets under a restrictive CSP. Tokens stay in page memory, never
URLs, browser storage, source files or request logs. Authentication is rechecked
after reading a write request. At most 16 connections are handled concurrently.
This is not a production rate-limiter or a replacement for TLS at non-loopback
boundaries; the server deliberately does not offer a public bind option.

The new UI displays the authenticated subject, roles, top-level execution
provenance, deterministic metrics, legacy/verified review history, a technical
JSON panel and role-gated controls. It clears stale evidence after failed loads
or credential changes. Existing accepted runs have no further form to complete.
Administrators can inspect and explicitly reconcile managed jobs.

### Managed workers

`managed_worker.py` starts **systemd user services**, not scopes whose lifetime
depends on the launching shell. systemd owns the cgroup; worker delegation is
explicitly disabled. Each job has CPU, memory, task, wall-clock and stop limits,
`KillMode=control-group`, SIGKILL escalation, no automatic restart and no-new-
privileges. Effective `cpu.max`, `memory.max` and `pids.max` values are checked
before normal monitoring continues. `ProtectControlGroups` denies direct cgroup
modification by the worker. A new session/process group does not escape its
service cgroup.

A private launch file transfers only allowlisted environment values. The worker
consumes and deletes it before exec. Review/identity secrets are not forwarded.
Fixture workers do not receive JDBC credentials. Secret files never enter the
job database or journal. A crashed launcher can leave a protected launch file;
confirmed reconciliation removes it. File privacy requires a Linux owner-only
state directory, normally under `$HOME/.local/state`, not a permissive Windows
mount. Private credential files are not encrypted at rest.

Persistent SQLite job intent/events and an exclusive lock gate new submissions.
Any non-final job blocks later work, including after supervisor SIGKILL. The
service manager still owns the child and enforces its runtime bound. Recovery
requires an authenticated administrator, expected revision, idempotency key and
reason. It stops the unit, confirms cgroup emptiness, hashes any retained receipt
and appends recovery evidence. It never reruns source/model calls. Resource limits contain the local agent,
its JVM and helper descendants; they do not constrain or guarantee cancellation
of separate Windows Ollama or Zetaris server processes. A recovered
candidate is still awaiting human review. A lost final acknowledgement is
replayed from the committed event, without repeating external operations.

There is no distributed queue. State-directory ownership is local, and same-user
host administrators remain trusted. Cgroups are not a complete sandbox against
hostile code with access to the same user's service-manager bus. A dedicated
service account and deployment-specific IPC restrictions remain separate work.

## Tests that do not need an identity provider or systemd

From the new worktree, with Python 3.12+ and Node available:

```bash
python -m pip install --upgrade -r requirements-identity.txt
export PYTHONPATH="$PWD/src"
python scripts/verify_identity_worker.py --focused
python scripts/verify_identity_worker.py
```

The first command runs only this slice. The second runs all repository tests.
Verification writes uniquely named logs, source hashes, the current Git SHA and
dirty status, dependency versions and real process exit codes under `runtime/`.
A test failure cannot be hidden by `tee`. It does not contact real Zetaris,
Ollama or an identity provider. Tokens and RSA keys in tests are generated fixture
material, never user credentials. HTTP tests run real localhost requests and
actual RSA verification against a controlled provider transport.

For the existing deterministic fixtures, H-MEM and wheel isolation checks:

```bash
python scripts/verify_identity_worker.py --fixtures
```

Node 24 is required by the existing H-MEM bridge. Do not call a skipped or blocked
integration test a pass. The previous operator-reported 178 tests are historical
baseline evidence, not proof that this branch's complete suite has run.

## Real systemd checks: an explicit option

```bash
python -m afyaevidence.managed_worker preflight
python scripts/check_managed_systemd.py --run
```

Preflight requires non-root Linux, systemd 254+, cgroup v2 with CPU/memory/PID
controllers and a working user service manager. `PREFLIGHT_PASS` is **not**
containment acceptance. The second command creates only harmless temporary
synthetic probe services and tests cancellation, a child in a different session,
launcher SIGKILL/replacement blocking, administrator recovery and runtime expiry.
It does not run the real agent, contact JDBC/Ollama or change existing job records.
Unavailable capabilities return `LIVE_SYSTEMD=BLOCKED` with exit 2. This environment
cannot establish WSL user-manager/controller delegation on the user's machine.

After that check passes, a supervised synthetic scripted run is optional:

```bash
python -m afyaevidence.managed_worker run --project "$PWD" -- \
  --data-mode fixture --snapshot "$PWD/data/synthetic/fx_32e8b610" \
  --model-provider scripted --execution-profile cpu --memory disabled_fixture
python -m afyaevidence.managed_worker audit
```

The launcher chooses a new private receipt path. Caller-supplied `--output`, shell
commands and unsupported/duplicate arguments are rejected. The audit does not
convert an empty history into a recovery success claim. Unfinished jobs must be
inspected/reconciled, not deleted to clear the gate.

## Live identity acceptance: requires real configuration

Do not substitute the original `AFYA_REVIEW_TOKEN` or a locally invented identity
for a provider access token. Configure the real issuer, audience, JWKS URL,
introspection client and role mapping in a **private copy** of
`config/identity.example.json`. The example values are non-functional placeholders.
Use a private path outside Git, and supply the client secret in the named
environment variable. Do not paste tokens or secrets into chat/screenshots.

Prepare a separate database copy using the original checkout's actual path:

```bash
python scripts/prepare_identity_review.py \
  --source "/absolute/path/to/original/afyaevidence/runtime/reviews.sqlite3" \
  --destination runtime/identity-review.sqlite3
read -rsp 'OIDC introspection client secret: ' AFYA_OIDC_CLIENT_SECRET; echo
export AFYA_OIDC_CLIENT_SECRET
python -m afyaevidence.identity_review_server \
  --db runtime/identity-review.sqlite3 \
  --identity-config "$HOME/.config/afyaevidence/identity.json" \
  --managed-state "$HOME/.local/state/afyaevidence-managed" \
  --port 8011
```

Copy fails rather than overwriting an existing destination. The original database
is opened read-only for SQLite backup, including committed WAL content. No
re-import or repeat approval of the existing accepted run is necessary. Its
original `accept` revision 1 must remain a **legacy unverified identity** entry.
Use a new synthetic unreviewed run to validate a new individual reviewer decision.
Verify viewer denial, reviewer success, administrator-only recovery, expiry,
revocation and provider outage with the actual provider before live acceptance.

## Security/release limitations

Implemented controls are not a certification or an independent penetration test.
Live identity-provider integration, real systemd/OOM/host-reboot acceptance,
TLS/reverse-proxy integration, dependency locking/vulnerability review, backup-
restore drills, fleet monitoring, stronger host isolation and independent
security review remain acceptance gates. The optional dependency requirements
state a compatibility range; retain the verifier's exact environment record and
create a reviewed deployment lock before release. No hosted CI success, production
readiness, medical approval or automatic merge is claimed.

## Primary implementation references

- PyJWT API, fixed allowed algorithms and issuer/audience validation:
  https://pyjwt.readthedocs.io/en/stable/api.html
- systemd transient service lifecycle and environment expansion:
  https://www.freedesktop.org/software/systemd/man/latest/systemd-run.html
- systemd cgroup termination semantics:
  https://www.freedesktop.org/software/systemd/man/systemd.kill.html

These references informed the implementation; they do not independently validate
this deployment or its configuration.
