#!/usr/bin/env bash
# Read-only assessment of a pinned Keycloak candidate's Java trust and 2D exposure.
# This provides evidence, not a CVE fix or a production approval.
set -Eeuo pipefail
IMAGE='quay.io/keycloak/keycloak@sha256:3e1ac632e743660017b1e6bb4c3ffc800fd02c82cdd0db858cd03456a98a8dfc'
PINNED_MANIFEST='sha256:3e1ac632e743660017b1e6bb4c3ffc800fd02c82cdd0db858cd03456a98a8dfc'
EXPECTED_CONFIG='sha256:b55801be6ce15109868bd056dc18d62d47106bfaad7ffbd1a5d804192ec98257'
# Docker's containerd image store may report a manifest digest in .Id,
# whereas the classic store reports the config digest. Neither representation
# alone should silently authorise an unpinned image. Check the *exact* pinned
# repository digest as well as the recognised Docker image identifier.
ACTUAL="$(docker image inspect "$IMAGE" --format '{{.Id}}')" || {
  echo 'CANDIDATE_IMAGE=BLOCKED'; exit 2;
}
DIGESTS="$(docker image inspect "$IMAGE" --format '{{range .RepoDigests}}{{println .}}{{end}}')" || {
  echo 'CANDIDATE_REPOSITORY_DIGEST=BLOCKED'; exit 2;
}
# Read Docker's output one digest per line. Exact Bash string comparison
# avoids format-escaping errors and cannot accept a similar or shortened digest.
PIN_MATCH=0
while IFS= read -r digest; do
  if [[ "$digest" == "$IMAGE" ]]; then
    PIN_MATCH=1
    break
  fi
done <<< "$DIGESTS"
if [[ "$PIN_MATCH" -ne 1 ]]; then
  echo 'CANDIDATE_PINNED_REPOSITORY_DIGEST=FAIL'
  exit 2
fi
echo 'CANDIDATE_PINNED_REPOSITORY_DIGEST=PASS'
if [[ "$ACTUAL" == "$PINNED_MANIFEST" ]]; then
  echo 'CANDIDATE_DOCKER_ID_KIND=MANIFEST'
elif [[ "$ACTUAL" == "$EXPECTED_CONFIG" ]]; then
  echo 'CANDIDATE_DOCKER_ID_KIND=CONFIGURATION'
else
  echo 'CANDIDATE_IDENTITY=FAIL'
  printf 'ACTUAL_DOCKER_IMAGE_ID=%s\n' "$ACTUAL"
  exit 2
fi
echo 'CANDIDATE_IDENTITY=PASS'
docker run --rm --pull never --network none --read-only --entrypoint /bin/bash "$IMAGE" -c '
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
# Capture the *whole* successful listing before searching it; a failed
# verbose listing must not be mistaken for the absence of a root certificate.
if ! CERT_LIST="$("$KEYTOOL" -list -keystore "$CA" -storepass changeit -v 2>/dev/null)"; then
  echo "JAVA_CERTIFICATE_LIST=BLOCKED_UNREADABLE_STORE"
  exit 2
fi
echo "JAVA_CERTIFICATE_LIST=PASS"
if [[ "$CERT_LIST" =~ Owner:.*(emSign[[:space:]]ECC[[:space:]]Root[[:space:]]CA[[:space:]]-[[:space:]]G3|eMudhra) ]]; then
  echo "EMUDHRA_ROOT_MATCH=FOUND_REQUIRES_REVIEW"
else
  echo "EMUDHRA_ROOT_MATCH=NOT_FOUND_IN_KEYTOOL_OUTPUT_NOT_PROOF_OF_MITIGATION"
fi
if command -v java >/dev/null 2>&1; then
  if ! MODULE_LIST="$(java --list-modules 2>/dev/null)"; then
    echo "JAVA_MODULE_LIST=BLOCKED"
    exit 2
  fi
  if [[ "$MODULE_LIST" =~ (^|
    echo "JAVA_DESKTOP_MODULE=PRESENT"
  else
    echo "JAVA_DESKTOP_MODULE=NOT_LISTED"
  fi
else
  echo "JAVA_RUNTIME=BLOCKED_UNAVAILABLE"
  exit 2
fi
echo "CVE_2026_91403=REQUIRES_VENDOR_REVIEW"
echo "CVE_2026_91415=REQUIRES_EXPOSURE_AND_VENDOR_REVIEW"
echo "CONTAINER_RELEASE=BLOCKED"
'
\n')java[.]desktop@ ]]; then
    echo "JAVA_DESKTOP_MODULE=PRESENT"
  else
    echo "JAVA_DESKTOP_MODULE=NOT_LISTED"
  fi
else
  echo "JAVA_RUNTIME=BLOCKED_UNAVAILABLE"
  exit 2
fi
echo "CVE_2026_91403=REQUIRES_VENDOR_REVIEW"
echo "CVE_2026_91415=REQUIRES_EXPOSURE_AND_VENDOR_REVIEW"
echo "CONTAINER_RELEASE=BLOCKED"
'
