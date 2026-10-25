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
# Parse keytool output using Bash only; avoid awk and writable temporary files.
MATCH_COUNT=0
CERT_ALIAS=UNKNOWN
CERT_ENTRY=UNKNOWN
CERT_OWNER=UNKNOWN
CERT_SHA=UNKNOWN
CERT_STARTED=0
shopt -s nocasematch
emit_certificate() {
  if [[ "$CERT_OWNER" == *emudhra* || "$CERT_OWNER" == *"emSign ECC Root CA - G3"* ]]; then
    MATCH_COUNT=$((MATCH_COUNT + 1))
    printf "MATCHING_CERTIFICATE_ALIAS=%s\n" "$CERT_ALIAS"
    printf "MATCHING_CERTIFICATE_ENTRY_TYPE=%s\n" "$CERT_ENTRY"
    printf "MATCHING_CERTIFICATE_SUBJECT=%s\n" "$CERT_OWNER"
    printf "MATCHING_CERTIFICATE_SHA256=%s\n" "$CERT_SHA"
    echo "MATCHING_CERTIFICATE_METADATA_END=1"
  fi
}
while IFS= read -r LINE; do
  case "$LINE" in
    "Alias name:"*)
      if [[ "$CERT_STARTED" == 1 ]]; then emit_certificate; fi
      CERT_STARTED=1
      CERT_ALIAS="${LINE#Alias name: }"
      CERT_ENTRY=UNKNOWN; CERT_OWNER=UNKNOWN; CERT_SHA=UNKNOWN
      ;;
    "Entry type:"*) CERT_ENTRY="${LINE#Entry type: }" ;;
    "Owner:"*) CERT_OWNER="${LINE#Owner: }" ;;
    *)
      if [[ "$LINE" =~ ^[[:space:]]*SHA256:[[:space:]]*(.*)$ && "$CERT_SHA" == UNKNOWN ]]; then
        CERT_SHA="${BASH_REMATCH[1]}"
      fi
      ;;
  esac
done < <(printf "%s\n" "$CERT_LIST")
if [[ "$CERT_STARTED" != 1 ]]; then
  echo "CERTIFICATE_METADATA=BLOCKED_NO_ALIAS_RECORDS"; exit 2
fi
emit_certificate
shopt -u nocasematch
printf "MATCHING_CERTIFICATE_COUNT=%s\n" "$MATCH_COUNT"
echo "CERTIFICATE_METADATA=PASS"
if (( MATCH_COUNT > 0 )); then
  echo "EMUDHRA_ROOT_MATCH=FOUND_REQUIRES_REVIEW"
else
  echo "EMUDHRA_ROOT_MATCH=NOT_FOUND_IN_KEYTOOL_OUTPUT_NOT_PROOF_OF_MITIGATION"
fi
if command -v java >/dev/null 2>&1; then
  if ! MODULE_LIST="$(java --list-modules 2>/dev/null)"; then
    echo "JAVA_MODULE_LIST=BLOCKED"
    exit 2
  fi
  if [[ "$MODULE_LIST" =~ java[.]desktop@ ]]; then
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
