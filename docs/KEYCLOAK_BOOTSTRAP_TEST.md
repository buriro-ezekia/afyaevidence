## Local Keycloak realm/bootstrap execution (22 October 2026)

The previous operator reported `KEYCLOAK_REALM_DISCOVERY=PASS` for the
`afya-local` realm using trusted HTTPS, and Docker 29.9.2. This is
discovery-only evidence; no human access tokens have been accepted yet.

`scripts/bootstrap_keycloak_realm.py` uses **the local HTTPS admin API**,
reads the local bootstrap administrator credentials from the private,
owner-restricted `~/.local/state/afyaevidence-keycloak-local/bootstrap.env`
file, and creates missing named resources:
- realm `afya-local` (300-second access-token lifetime)
- confidential client `afya-review-introspection` with browser flows and
  direct grants disabled
- public authorisation-code PKCE client `afya-human-login` with a
  single 127.0.0.1 callback
- three realm role definitions: `viewer`, `reviewer`, `administrator`

Run inside the detached Keycloak integration worktree:

```bash
cd "$HOME/afyaevidence-keycloak-live"
git fetch origin
git switch --detach origin/work/keycloak-live-acceptance
source "$HOME/.venvs/afyaevidence-identity/bin/activate"
export PYTHONPATH="$PWD/src"
python -m py_compile scripts/bootstrap_keycloak_realm.py
python scripts/bootstrap_keycloak_realm.py
python scripts/check_keycloak_realm.py
```

**Expected**: `KEYCLOAK_BOOTSTRAP=PASS` and
`KEYCLOAK_REALM_DISCOVERY=PASS`. The bootstrap script is create-only:
pre-existing resources are not overwritten, not reconciled and not
automatically approved; inspect any existing clients in the Admin Console
before relying on them.

**Outstanding explicit blockers:** do not claim `LIVE_USER_AUTH=PASS`.
Configure Keycloak's access-token `typ=at+jwt` setting, flat
list-valued `roles` protocol mapper, exact single-string resource
audience, and the introspection claim shapes required by
`identity_auth.py`. Create three separate test human accounts and use
the browser authorisation-code PKCE flow (not password grant) to obtain
their individual short-lived access tokens. The bootstrap administrator
login uses Keycloak's special admin-cli password grant strictly for
local administrative setup, **not for reviewer authentication**.

No private keys or passwords should be pasted into GitHub or chat. Neither
this script nor the discovery test writes to AfyaEvidence review tables.
Use `scripts/check_keycloak_live.py` only after all token compatibility
requirements have been established, with the private client secret in
`AFYA_OIDC_CLIENT_SECRET`, and record provider outages/revocation as
separate live tests.

