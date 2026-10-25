#!/usr/bin/env bash
# Read-only assessment of a pinned Keycloak candidate's Java trust and 2D exposure.
# This provides evidence, not a CVE fix or a production approval.
set -Eeuo pipefail
IMAGE='quay.io/keycloak/keycloak@sha256:3e1ac632e743660017b1e6bb4c3ffc800fd02c82cdd0db858cd03456a98a8dfc'
EXPECTED='sha256:b55801be6ce15109868bd056dc18d62d47106bfaad7ffbd1a5d804192ec98257'
ACTUAL="$(docker image inspect "$IMAGE" --format '{{.Id}}')" || {
  echo 'CANDIDATE_IMAGE=BLOCKED'; exit 2;
}
if [[ "$ACTUAL" != "$EXPECTED" ]]; then
  echo 'CANDIDATE_IDENTITY=FAIL'
  printf 'ACTUAL_LOCAL_CONFIG_ID=%s\nEXPECTED_REMOTE_CONFIG_ID=%s\n' "$ACTUAL" "$EXPECTED"
  echo 'PINNED_MANIFEST=sha256:3e1ac632e743660017b1e6bb4c3ffc800fd02c82cdd0db858cd03456a98a8dfc'
  echo 'IDENTITY_ACTION=INSPECT_LOCAL_IMAGE_AND_REGISTRY_MANIFEST'
  exit 2
fi
echo 'CANDIDATE_IDENTITY=PASS'
docker run --rm --network none --read-only --entrypoint /bin/bash "$IMAGE" -c '
set -euo pipefail
CA=/etc/pki/java/cacerts
test -s "$CA" || { echo "JAVA_CA_STORE=FAIL"; exit 2; }
test "$(readlink -f "$CA")" = /etc/pki/ca-trust/extracted/java/cacerts || {
  echo "JAVA_CA_LINKAGE=FAIL"; exit 2;
}
echo "JAVA_CA_LINKAGE=PASS"
KEYTOOL=/usr/bin/keytool
if ! command -v "$KEYTOOL" >/dev/null 2>&1; then
  if command -v keytool >/dev/null 2>&1; then KEYTOOL="$(command -v keytool)"
  else echo "JAVA_KEYTOOL=BLOCKED_UNAVAILABLE"; exit 2
  fi
fi
echo "JAVA_KEYTOOL=FOUND"
# Trust-store listing is read-only. The standard vendor default store
# password is not an application credential.
if ! "$KEYTOOL" -list -keystore "$CA" -storepass changeit >/dev/null 2>&1; then
  echo "JAVA_KEYTOOL=BLOCKED_UNREADABLE_STORE"
  exit 2
fi
if "$KEYTOOL" -list -keystore "$CA" -storepass changeit -v 2>/dev/null |
  grep -Eiq "Owner:.*emSign ECC Root CA - G3|Owner:.*eMudhra"; then
  echo "EMUDHRA_ROOT_MATCH=FOUND_REQUIRES_REVIEW"
else
  echo "EMUDHRA_ROOT_MATCH=NOT_FOUND_IN_KEYTOOL_OUTPUT"
fi
if command -v java >/dev/null 2>&1; then
  if java --list-modules 2>/dev/null | grep -q "^java.desktop@"; then
    echo "JAVA_DESKTOP_MODULE=PRESENT"
  else
    echo "JAVA_DESKTOP_MODULE=NOT_LISTED"
  fi
else
  echo "JAVA_RUNTIME=BLOCKED_UNAVAILABLE"
fi
echo "CVE_2026_91403=REQUIRES_VENDOR_REVIEW"
echo "CVE_2026_91415=REQUIRES_EXPOSURE_AND_VENDOR_REVIEW"
echo "CONTAINER_RELEASE=BLOCKED"
'
