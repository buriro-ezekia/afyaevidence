#!/usr/bin/env bash
# Isolated HTTPS Keycloak developer instance. Does not initialise any AfyaEvidence database.
set -Eeuo pipefail
for cmd in docker openssl python3 curl; do
  command -v "$cmd" >/dev/null || { echo "BLOCKED: missing $cmd"; exit 2; }
done
STATE="${HOME}/.local/state/afyaevidence-keycloak-local"
HOST="localhost"
NAME="afyaevidence-keycloak-local"
mkdir -p "$STATE/tls"
chmod 700 "$STATE" "$STATE/tls"
if [[ ! -f "$STATE/tls/tls.crt" || ! -f "$STATE/tls/tls.key" ]]; then
  if [[ -e "$STATE/tls/tls.crt" || -e "$STATE/tls/tls.key" ]]; then
    echo "BLOCKED: partial certificate state; inspect manually"; exit 2
  fi
  openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 30 \
    -keyout "$STATE/tls/tls.key" -out "$STATE/tls/tls.crt" \
    -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost" >/dev/null 2>&1
  chmod 600 "$STATE/tls/tls.key"
fi
if [[ ! -f "$STATE/bootstrap.env" ]]; then
  umask 077
  python3 - "$STATE/bootstrap.env" <<'PY'
import secrets,sys
from pathlib import Path
p=Path(sys.argv[1])
with p.open("x") as f:
    f.write("KC_BOOTSTRAP_ADMIN_USERNAME=afya-local-admin\\n")
    f.write("KC_BOOTSTRAP_ADMIN_PASSWORD="+secrets.token_urlsafe(36)+"\\n")
p.chmod(0o600)
PY
fi
if docker container inspect "$NAME" >/dev/null 2>&1; then
  echo "KEYCLOAK_CONTAINER=EXISTS: never automatically overwrite or reset existing realm"
  docker ps --filter "name=^/${NAME}$" --format '{{.Names}} {{.Status}}'
else
  docker volume create afyaevidence-keycloak-data >/dev/null
  docker run -d --name "$NAME" --restart no \
    -p 127.0.0.1:8443:8443 --memory 2g \
    --env-file "$STATE/bootstrap.env" \
    -e KC_HOSTNAME=https://localhost:8443 \
    -e KC_HTTPS_CERTIFICATE_FILE=/opt/keycloak/conf/local-tls/tls.crt \
    -e KC_HTTPS_CERTIFICATE_KEY_FILE=/opt/keycloak/conf/local-tls/tls.key \
    -v "$STATE/tls:/opt/keycloak/conf/local-tls:ro" \
    -v afyaevidence-keycloak-data:/opt/keycloak/data \
    quay.io/keycloak/keycloak:26.8.1 start-dev >/dev/null
  echo "KEYCLOAK_CONTAINER=STARTED"
fi
echo "KEYCLOAK_TLS_URL=https://localhost:8443/"
echo "KEYCLOAK_LOCAL_CA=$STATE/tls/tls.crt"
echo "KEYCLOAK_LOCAL_CA_VALIDITY=30_DAYS"
echo "KEYCLOAK_ADMIN_PASSWORD=PRIVATE_AT_$STATE/bootstrap.env"
echo "LIVE_KEYCLOAK=NOT_TESTED"
echo "Next check: curl --fail --cacert \"$STATE/tls/tls.crt\" https://localhost:8443/realms/master/.well-known/openid-configuration"
