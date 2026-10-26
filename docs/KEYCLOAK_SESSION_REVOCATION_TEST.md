# Live session logout/revocation acceptance

This is a **one-time, local test** against the disposable Keycloak
development instance and the existing read-only synthetic run. The viewer
must obtain a fresh access and refresh token via the browser PKCE flow.
The script retains both only in process memory; no JWT, refresh token,
authorisation code or password is printed, persisted or transmitted to
chat/GitHub.

## Terminal 1 — identity-aware AfyaEvidence API

Leave the application listening on `127.0.0.1:8012`, pointing **only** to
`runtime/live-http-acceptance.sqlite3`. Do not use the original database
or repeat the already-finalised reviewer write. Keycloak must also be
running over trusted HTTPS on `localhost:8443`.

## Terminal 2 — single-session revocation test

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
  --role viewer --revocation-test --http-port 8012
```

Open the script's new login URL in a fresh private browser window and
authenticate only as `afya-test-viewer`. The script must first obtain
HTTP 200 for the already-finalised synthetic run (a **GET only**), submit
the **fresh public-client refresh token** to Keycloak's OpenID Connect
logout endpoint, and require the same access token to receive HTTP 401
from the identity-aware API thereafter. Keycloak remains online.

Expected status:
```
PKCE_LOGIN=PASS
REVOCATION_PRE_HTTP=200
KEYCLOAK_SESSION_LOGOUT=PASS
REVOCATION_POST_HTTP=401
LIVE_REVOCATION=PASS
REVIEW_WRITE=NOT_RUN
```

If Keycloak omits a refresh token, rejects public-client logout, or does
not invalidate the original access token within the bounded 8-second
observation window, the test returns BLOCKED/FAIL—not an assumed PASS.
Do not weaken online introspection, remove signature verification or
change any review record to get a passing result.

**Scope:** Validates invalidation of one freshly established interactive
viewer session, not arbitrary administrative revocation, every logout
mechanism, global revocation semantics, production session lifecycle or
independent security review. The local test will sign out that fresh
session. Keep PRs draft/unmerged.
