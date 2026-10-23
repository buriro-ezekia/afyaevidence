# Live Keycloak HTTP role acceptance — isolated synthetic database only

The local identity-aware API on port 8011 has already returned HTTP 401 for
missing and invalid tokens, and the operator confirmed that the synthetic
`run_pending` row remains at revision 0 without a disposition.

`scripts/check_keycloak_pkce.py --http-role-test` uses a fresh browser PKCE
login for each role and forwards the verified short-lived bearer token only
to the local 127.0.0.1:8011 server. Tokens are not printed or persisted.
This deliberately targets only the isolated
`runtime/live-http-acceptance.sqlite3` test fixture containing
`run_pending` and `run_legacy`. Do not point the server at the original
or previously accepted production/development review database.

## Environment and ordering

Keep Keycloak HTTPS at `https://localhost:8443` and the identity-aware
API running separately on localhost:8011, configured against the isolated
fixture and private Keycloak identity configuration. In a second Ubuntu
terminal, do:

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
```

Run **in this exact order** (one at a time, in separate fresh private
browser sessions; use the account matching the role):

```bash
python scripts/check_keycloak_pkce.py --identity-config "$HOME/.config/afyaevidence/keycloak-local.json" --role viewer --http-role-test
python scripts/check_keycloak_pkce.py --identity-config "$HOME/.config/afyaevidence/keycloak-local.json" --role administrator --http-role-test
python scripts/check_keycloak_pkce.py --identity-config "$HOME/.config/afyaevidence/keycloak-local.json" --role reviewer --http-role-test
```

Viewer and administrator each must show:
```
LIVE_HTTP_EVIDENCE_READ=PASS
LIVE_HTTP_<ROLE>_WRITE_DENIED=PASS
LIVE_HTTP_REVIEW_STATE_UNCHANGED=PASS
LIVE_HTTP_ROLE=PASS
```

The reviewer must show:
```
LIVE_HTTP_EVIDENCE_READ=PASS
LIVE_HTTP_REVIEWER_WRITE=PASS
LIVE_HTTP_VERIFIED_AUDIT=PASS
LIVE_HTTP_ROLE=PASS
```

The reviewer POST is a **real, one-time mutation** of the *disposable test
fixture*: `run_pending` receives `request_more_evidence`, revision 1,
and a verified OIDC audit grant. This is not a clinical review or a
change to the existing accepted run. A rerun against the same fixture
will correctly report `BLOCKED`, because it is no longer unreviewed.
Never reset/delete a failed or incomplete job or the original review
database merely to make a test pass.

Read-only final validation:

```bash
python - <<'PY'
import sqlite3
from pathlib import Path
p=Path.home()/'afyaevidence-keycloak-live/runtime/live-http-acceptance.sqlite3'
with sqlite3.connect(f'file:{p}?mode=ro',uri=True) as db:
    pending=db.execute("SELECT revision,disposition FROM runs WHERE run_id='run_pending'").fetchone()
    legacy=db.execute("SELECT revision,disposition FROM runs WHERE run_id='run_legacy'").fetchone()
    grant=db.execute("SELECT COUNT(*) FROM verified_review_grants WHERE run_id='run_pending'").fetchone()[0]
assert pending==(1,'request_more_evidence') and legacy==(1,'accept') and grant==1
print('LIVE_HTTP_SYNTHETIC_REVIEW=PASS')
print('LEGACY_FIXTURE_PRESERVED=PASS')
PY
```

This does **not** establish actual token revocation, deliberate provider
outage behaviour, independent security review, production deployment,
or clinical approval. Draft PR #4 and prior PRs stay unmerged.
