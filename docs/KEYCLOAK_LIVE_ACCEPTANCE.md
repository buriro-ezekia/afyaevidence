# Keycloak live acceptance for AfyaEvidence (draft, local-only)

**Scope:** separate integration branch based on PR #3 commit `945e27d`. This
does not modify PR #3 or the historical accepted review. This is an operator
runbook; no actual Keycloak instance, credentials or live verification have
been provisioned by GitHub commits.

## Why this configuration is strict

AfyaEvidence `identity_auth.py` is an **OAuth resource server**, not a login
application. It requires:
- Trusted HTTPS issuer, JWKS and introspection URLs, with issuer and exact
  string audience matching the signed JWT and introspection response.
- RS256, an access-token **header** `typ: at+jwt` (NOT `JWT`),
  `sub`, `jti`, `iat`, `exp`, and a flat **list** claim `roles`. The optional `nbf` claim is validated when supplied; when absent, the verified `iat` serves as the lower time bound.
- Three distinct accounts, each assigned exactly one of `viewer`,
  `reviewer`, `administrator`, and a token lifetime up to 900 seconds.
- Confidential introspection client credentials and **online introspection on
  every request**. Inactive/revoked or unavailable responses fail closed.

Keycloak defaults differ: role claims are normally nested under
`realm_access.roles` / `resource_access`, and `typ` is normally
`JWT`. You MUST configure the protocol mappers and enable the client
advanced setting **Use "at+jwt" as access token header type**. Do not relax
AfyaEvidence verification to accept the defaults.

## Local identity-provider setup

Use a *test-only* Keycloak 26.8.1 or a currently supported version verified
against its documentation. A Docker development server on HTTP
`127.0.0.1:8080` **cannot** be used directly as the AfyaEvidence issuer,
which correctly refuses non-HTTPS URLs.

For an isolated WSL test instance, configure Keycloak HTTPS with a certificate
valid for a consistent hostname (e.g. `afya-id.localhost`), place TLS keys
outside the repository with owner-only permissions, and trust the test CA in
the WSL Python trust store. Prefer a separately configured HTTPS reverse proxy
for realistic deployments. Do not use `verify=False`, HTTP issuer URLs,
self-signed certificates without explicit trust, ambient proxies or
certificate-error overrides. Keep all development ports loopback-bound.

In the Keycloak Admin Console:

1. Create realm `afya-local`. Set `https://afya-id.localhost:8443/realms/afya-local`
   as the issuer *only if that is the actual TLS endpoint*.
2. Create confidential client `afya-review-introspection`, turn client
   authentication ON, and retain its secret privately. Add this client as the
   audience of tokens. Verify introspection with the client: recent Keycloak
   releases can require the caller to be included in the token audience.
3. Create a separate interactive public PKCE client for individual human
   login. Allow only a deliberate localhost callback and require PKCE S256.
   Disable implicit flow; do not use a password grant or service-account
   token in place of a human reviewer.
4. Configure protocol mappers so the access token has a flat, list-valued
   `roles` claim holding only the application role(s); include the `roles`
   mapper in access token and introspection. Limit client role scope;
   disable broad `Full Scope Allowed` where appropriate.
5. In client Advanced / Fine grain OpenID Connect configuration, turn ON
   **Use "at+jwt" as access token header type** for the token-issuing client.
6. Configure the audience mapper so the **single string** `aud` in each
   token is `afya-review-introspection` (the intended resource audience);
   check the exact token payload. If the actual `aud` is a list or contains
   additional audiences, it is **not compatible** with current
   `strict_aud=True`: treat the integration as BLOCKED, not PASS.
7. Create **three different human test accounts** (viewer, reviewer,
   administrator) and grant only the corresponding application role.
   Ensure all use short-lived access tokens (<=900 seconds). No service account
   may be presented as a human.
8. Obtain fresh tokens through the public client's browser authorisation-code
   flow with PKCE, using a trusted local test client. Never paste passwords,
   access tokens, admin secrets or private keys into GitHub or chat.

**Provider contract gate:** Prior to acceptance verify that introspection
returns `active=true`, `iss`, `aud`, `sub`, `exp` identical to the signed
JWT. Some Keycloak configurations omit `iss` in introspection or add extra
audiences. These are compatibility blockers until a documented, tested
provider-specific adapter is implemented. Do not silently relax comparison.

## Private AfyaEvidence configuration

Put the following outside Git, e.g.
`$HOME/.config/afyaevidence/keycloak-local.json` (mode 0600).
Replace hostname and audience to match the **real** issuer and audience.

```json
{
  "issuer": "https://afya-id.localhost:8443/realms/afya-local",
  "audience": "afya-review-introspection",
  "jwks_uri": "https://afya-id.localhost:8443/realms/afya-local/protocol/openid-connect/certs",
  "introspection_uri": "https://afya-id.localhost:8443/realms/afya-local/protocol/openid-connect/token/introspect",
  "client_id": "afya-review-introspection",
  "secret_env": "AFYA_OIDC_CLIENT_SECRET",
  "roles_claim": "roles",
  "token_type": "at+jwt",
  "max_lifetime_seconds": 900
}
```

Read the confidential client's secret **interactively** in the shell, without
typing or echoing it into a command line:

```bash
cd "$HOME/afyaevidence-identity-worker"
source "$HOME/.venvs/afyaevidence-identity/bin/activate"
export PYTHONPATH="$PWD/src"
read -rsp 'Keycloak introspection client secret: ' AFYA_OIDC_CLIENT_SECRET; echo
export AFYA_OIDC_CLIENT_SECRET
python scripts/check_keycloak_live.py --identity-config "$HOME/.config/afyaevidence/keycloak-local.json" --noninteractive
```

This first command is only a config check; it prints
`LIVE_KEYCLOAK=NOT_TESTED`, NOT a successful connection to the provider.

After acquiring short-lived human access tokens through PKCE, run the
interactive **read-only** verifier:

```bash
python scripts/check_keycloak_live.py \
  --identity-config "$HOME/.config/afyaevidence/keycloak-local.json"
```

It requests the three tokens privately (hidden input). **PASS** requires
three distinct verified subjects, exact expected roles, online introspection
on each token and proper permission denials. It never writes review history,
never prints tokens and reports `REVIEW_WRITE=NOT_RUN` and
`REVOCATION_TEST=NOT_RUN` honestly.

A full HTTP/browser acceptance subsequently requires a *new synthetic
unreviewed run* in a **backup** database using
`scripts/prepare_identity_review.py`; do not re-review the previously
accepted run. Revocation and provider-outage tests must be performed using
that isolated environment and cannot be inferred from these role checks.

## Status and gates

### Updated operator evidence (23–25 October 2026)

The original steps below were written before the local Keycloak realm was
provisioned. Subsequent operator testing reported successful PKCE sign-in,
signed-token verification and live introspection for the distinct viewer,
reviewer and administrator accounts. In the disposable synthetic review
database, viewer and administrator review submissions were denied, while
the reviewer submitted one auditable decision. The operator also reported
HTTP 503 while Keycloak was unavailable, HTTP 401 for a token after session
logout, restoration of login after an outage, and 232 passing regression
tests. These are local observations, not hosted CI or an independent audit.

The Keycloak candidate image remains **blocked for production**:
CVE-2026-91403 and CVE-2026-91415 are still reported in its OpenJDK RPM.
The candidate contains the corrected CA certificate package and the Java
trust store points to that system store; whether this provides complete
mitigation for the former advisory requires independent review.
See [Keycloak residual risk](KEYCLOAK_RESIDUAL_SECURITY.md) and
[project completeness](PROJECT_COMPLETENESS_AUDIT.md).

### Original runbook baseline (retained for traceability)

- Earlier operator evidence: 231/231 automated tests, LIVE_SYSTEMD=PASS,
  supervised scripted synthetic job FINALISED.
- GitHub PR #3: draft/unmerged, Codex review blocked by usage limits.
- **Live Keycloak: NOT RUN**, pending actual provider, secure realm mapping,
  three individual test logins, introspection and verified claim shapes.
- **Live revocation, cross-role HTTP writes, deployment and independent
  security review: NOT RUN.**
- No clinical approval or production acceptance.

Official references:
- https://www.keycloak.org/getting-started/getting-started-docker
- https://www.keycloak.org/2025/04/keycloak-2620-released
- https://www.keycloak.org/docs/latest/server_admin/
- https://www.keycloak.org/securing-apps/oidc-layers
