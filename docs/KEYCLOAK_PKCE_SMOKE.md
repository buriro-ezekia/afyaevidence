# Test one real Keycloak human login (PKCE)

The prior operator check `OIDC_CONFIGURATION=PASS` is *not* live authentication.

This separate development script performs a browser authorisation-code login with
PKCE S256 for one of `viewer`, `reviewer`, or `administrator` and
immediately validates the resulting access token through AfyaEvidence's
existing strict OIDC resource server, **including online introspection**.
It never prints, writes or logs access/refresh tokens or auth codes, and
never writes a review or alters the existing review database.

## Preconditions

- The local Keycloak instance is running at `https://localhost:8443`,
  and the `afya-local` realm exists.
- Keycloak's public `afya-human-login` client allows **only**
  `http://127.0.0.1:8765/callback` as its loopback callback and uses
  authorisation code + PKCE S256, not implicit or password grant.
- The client issues RS256 access tokens with `typ=at+jwt`, exact string
  audience `afya-review-introspection` and top-level `roles: ["viewer"]`
  for the viewer test account. The Keycloak access token may omit optional `nbf`; signed `iat` is mandatory and future issue times remain rejected.
- The confidential client `afya-review-introspection` has an enabled
  credential, and introspection must return `active=true` plus matching
  `iss`, `aud`, `sub`, `exp`. If Keycloak's default response does not
  provide these, the script must FAIL—not weaken the verifier.
- A real local test **human** account `afya-test-viewer` has its own
  password and only the `viewer` AfyaEvidence role available in its token.
  Never use the bootstrap administrator or service account as reviewer.
- A **private** configuration file exists at
  `$HOME/.config/afyaevidence/keycloak-local.json`, and the introspection
  secret is available in an environment variable without printing it.

## Execute

```bash
cd "$HOME/afyaevidence-keycloak-live"
git fetch origin
git switch --detach origin/work/keycloak-live-acceptance

source "$HOME/.venvs/afyaevidence-identity/bin/activate"
source "$HOME/.nvm/nvm.sh"; nvm use 24
export PYTHONPATH="$PWD/src"
export SSL_CERT_FILE="$HOME/.local/state/afyaevidence-keycloak-local/tls/tls.crt"

python -m py_compile scripts/check_keycloak_pkce.py

read -rsp 'Private Keycloak introspection secret: ' AFYA_OIDC_CLIENT_SECRET; echo
export AFYA_OIDC_CLIENT_SECRET

python scripts/check_keycloak_pkce.py \
  --identity-config "$HOME/.config/afyaevidence/keycloak-local.json" \
  --role viewer
```

The script displays a per-login URL containing a transient state value and
PKCE challenge (but no password or token). Open it on the same computer in
a **new private/incognito browser window**. Sign in with the viewer account.
The browser returns only to the local callback on port 8765. The terminal
then performs code-for-token exchange, signature validation and mandatory
introspection; it prints only outcome flags.

Success requires:
```
PKCE_AUTHORIZATION_CODE=PASS
PKCE_SIGNED_ACCESS_TOKEN=PASS
PKCE_ONLINE_INTROSPECTION=PASS
PKCE_ROLE_VIEWER=PASS
PKCE_LOGIN=PASS
REVIEW_WRITE=NOT_RUN
REVOCATION=NOT_TESTED
```

On authentication or introspection failure, record the error **code only**.
Never post the displayed URL, encoded JWT, introspection secret or passwords.
Run the same process for separately created `reviewer` and
`administrator` test accounts only after the viewer path succeeds.
The current script verifies each role separately; it does not on its own
establish different account subjects across sessions.

**Acceptance limitations:** This is a non-production, single-user
authentication smoke test. It does not prove independent security review,
HTTP write permissions with a live provider, revocation recovery,
production TLS, operator identity proofing or clinical readiness.
