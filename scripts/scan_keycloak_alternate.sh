#!/usr/bin/env bash
# Inspect the exact local Keycloak image, without giving Trivy Docker-socket access.
set -Eeuo pipefail
IMAGE='quay.io/keycloak/keycloak:26.8.1'
EXPECTED_ID='sha256:79c623a22abacf3fe6c00a5fb30f5b7843d717b234033b80995891c06116d244'
SCANNER='aquasec/trivy:0.76.0'
OUT="${HOME}/afyaevidence-keycloak-live/runtime/security/trivy-alternate"
for cmd in docker python3 sha256sum; do
  command -v "$cmd" >/dev/null || { echo "KEYCLOAK_SCAN=BLOCKED_MISSING_${cmd^^}"; exit 2; }
done
IMAGE_ID="$(docker image inspect "$IMAGE" --format '{{.Id}}')" || { echo 'KEYCLOAK_SCAN=BLOCKED_IMAGE_MISSING'; exit 2; }
if [[ "$IMAGE_ID" != "$EXPECTED_ID" ]]; then
  echo 'KEYCLOAK_SCAN=BLOCKED_IMAGE_ID_MISMATCH'
  exit 2
fi
mkdir -p "$OUT/cache"
chmod 700 "$OUT"
ARCHIVE="$OUT/keycloak-image.tar"
if [[ ! -s "$ARCHIVE" ]]; then
  docker save --output "$ARCHIVE" "$IMAGE" || { echo 'KEYCLOAK_SCAN=BLOCKED_EXPORT_FAILED'; exit 2; }
fi
sha256sum "$ARCHIVE" > "$OUT/keycloak-image.tar.sha256"
# Download both the CVE and Java indexing databases from a supported mirror.
# Mount only a Docker image archive; never give the scanner a Docker socket.
scan_with() {
  local repo="$1"
  docker run --rm --network bridge \
    --mount "type=bind,src=$OUT,dst=/scan" \
    "$SCANNER" image --input /scan/keycloak-image.tar \
    --scanners vuln \
    --db-repository "${repo}/trivy-db:2" \
    --java-db-repository "${repo}/trivy-java-db:1" \
    --cache-dir /scan/cache \
    --format json --output /scan/keycloak-trivy.json \
    --exit-code 0
}
if ! scan_with 'public.ecr.aws/aquasecurity'; then
  echo 'KEYCLOAK_SCANNER_PRIMARY_DB=FAILED'
  if ! scan_with 'mirror.gcr.io/aquasec'; then
    echo 'KEYCLOAK_SCAN=BLOCKED_ALL_DB_MIRRORS_FAILED'
    exit 2
  fi
fi
python3 - "$OUT/keycloak-trivy.json" <<'PY'
import collections, json, pathlib, sys
p=pathlib.Path(sys.argv[1])
try:
    d=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(d,dict) or not isinstance(d.get('Results'),list):
        raise ValueError('missing_results')
    results=d['Results']
    if not results or not any(isinstance(r,dict) and r.get('Packages') for r in results):
        raise ValueError('incomplete_package_inventory')
    counts=collections.Counter()
    scanned=0
    for result in results:
        if not isinstance(result,dict):
            raise ValueError('invalid_result')
        if result.get('Class')=='lang-pkgs':
            scanned+=1
        for issue in result.get('Vulnerabilities') or []:
            counts[str(issue.get('Severity','UNKNOWN')).upper()]+=1
    print('KEYCLOAK_TRIVY_REPORT=PASS')
    print('KEYCLOAK_TRIVY_LANGUAGE_RESULT_SECTIONS='+str(scanned))
    for key in ('CRITICAL','HIGH','MEDIUM','LOW','UNKNOWN'):
        print('KEYCLOAK_CVES_'+key+'='+str(counts[key]))
    print('KEYCLOAK_CVES_TOTAL='+str(sum(counts.values())))
    print('KEYCLOAK_SCAN=COMPLETE_WITH_FINDINGS' if sum(counts.values()) else 'KEYCLOAK_SCAN=COMPLETE_NO_FINDINGS_REPORTED')
except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):
    print('KEYCLOAK_SCAN=BLOCKED_INVALID_REPORT')
    sys.exit(2)
PY
printf 'KEYCLOAK_REPORT_PATH=%s\n' "$OUT/keycloak-trivy.json"
