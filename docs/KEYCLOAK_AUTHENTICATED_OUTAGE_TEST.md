# Authenticated Keycloak outage acceptance

Previous operator baseline (23 Oct 2026): local listeners `127.0.0.1:8443`
and `127.0.0.1:8012`, `KEYCLOAK_BASELINE=PASS`, and
`AFYA_API_UNAUTH_STATUS=401`. Unauthenticated 401 during an outage is NOT
a proof of fail-closed authenticated requests.

## Terminal 1 — identity API (leave running)

Run `afyaevidence.identity_review_server` against the **isolated**
`runtime/live-http-acceptance.sqlite3` database on port 8012 with a private
introspection client secret and `SSL_CERT_FILE` referencing the trusted
local Keycloak certificate. Do **not** use the original review database.

## Terminal 2 — operator-driven outage test

```bash
cd "$HOME/afyaevidence-keycloak-live"
git fetch origin
git switch --detach origin/work/keycloak-live-acceptance
source "$HOME/.venvs/afyaevidence-identity/bin/activate"
export PYTHONPATH="$PWD/src"
export SSL_CERT_FILE="$HOME/.local/state/afyaevidence-keycloak-local/tls/tls.crt"
python -m py_compile scripts/check_keycloak_pkce.py
test -n "${AFYA_OIDC_CLIENT_SECRET:-}" || {
  read -rsp 'Keycloak introspection client secret: ' AFYA_OIDC_CLIENT_SECRET
  echo
  export AFYA_OIDC_CLIENT_SECRET
}
python scripts/check_keycloak_pkce.py \
  --identity-config "$HOME/.config/afyaevidence/keycloak-local.json" \
  --role viewer --authenticated-outage-test --http-port 8012
```

Authenticate in a fresh private browser window using only the viewer test
account. The script exchanges the PKCE code for a short-lived access token,
verifies it against Keycloak, then confirms a pre-outage authenticated API
read returns HTTP 200. It stops ONLY the matching locally named
`afyaevidence-keycloak-local` Docker container, calls the identity API
with the **same in-memory token**, and requires HTTP 503 (provider unavailable),
not 200. It attempts to restart Keycloak in a `finally` block and polls
trusted HTTPS discovery to confirm recovery.

Expected successful status lines:

```
PKCE_LOGIN=PASS
KEYCLOAK_OUTAGE_STOP=PASS
AUTHENTICATED_OUTAGE_HTTP=503
AUTHENTICATED_FAIL_CLOSED=PASS
KEYCLOAK_RECOVERY=PASS
AUTHENTICATED_OUTAGE=PASS
REVIEW_WRITE=NOT_RUN
REVOCATION=NOT_TESTED
```

**Limitations:** This temporarily disrupts the local Keycloak development
container and all sessions depending on it. Do not run if other people or
services rely on this instance. Automatic restart is best-effort, not
guaranteed after process/system power loss or Docker failure. If recovery
prints FAIL, inspect the container and use `docker start
afyaevidence-keycloak-local` in Terminal 2; do not delete volumes,
reinitialise the realm, loosen TLS or alter data. Do not paste the login
URL, access tokens, credentials or Docker secret variables into chat.

A PASS proves only **live identity-provider outage fail-closed behaviour** for
an otherwise valid, still-live viewer token during that particular local
test. It does not establish token revocation, production outage resistance,
independent security approval, deployment readiness or clinical approval.
The script performs **read-only GETs only**, not a second synthetic reviewer
disposition. Keep draft PR #4 unmerged.
