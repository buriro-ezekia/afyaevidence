# AfyaEvidence — project completeness and inconsistency audit

**Audit date:** 25 October 2026. **Branch:** `work/keycloak-live-acceptance` (draft PR #4). This is a repository/source and operator-evidence audit, not a fresh execution on the user's WSL host or independent security certification.

## Summary

AfyaEvidence is a working **synthetic evidence-review prototype**, with local verification across source inspection, fixture generation, agent orchestration, H-MEM, authenticated review, isolated human dispositions and systemd-managed workers. **Production and clinical release are not authorised.**

### Evidence matrix

| Workstream | Evidence observed | Remaining condition |
| --- | --- | --- |
| Data and source contracts | Fictional six-facility aggregate schema; 15 reproducible snapshots and 16 independent scenarios reported PASS | Real data governance/access and scope-specific acceptance |
| Investigation agent | 32 scripted executions in standard and CPU profiles reported PASS | Repeat live end-to-end verification per intended deployment |
| H-MEM | Reference integrity, persistence, provenance, chronology and outbox checks reported PASS | Production storage/security and real embedding evaluation |
| Local review | Historical accepted revision one preserved; hash-bound receipt evidence and human disposition implemented | Do not imply clinical approval |
| Identity | Three Keycloak roles passed PKCE signature, introspection and role checks; viewer/admin denied review, reviewer made one auditable synthetic disposition | Dedicated operational identity proofing and provider lifecycle at deployment |
| Availability | An otherwise valid access token received HTTP 503 while provider offline; a logged-out session token received HTTP 401; recovery passed | Multi-host failover and production monitoring |
| Managed worker | Real systemd containment and synthetic managed run reported PASS | Deployment service account, resource sizing, reboot and rollback drill |
| Regression and packaging | 232 Python tests, fixture evaluation, H-MEM, isolated wheel PASS | Hosted CI, reproducible dependency lock, artifact signing/SBOM |
| Python dependencies | Local pip 26.2.2, `pip check` clean, `pip-audit` 0 findings reported | Repeat on deployment lock/image |
| Keycloak container | Candidate rescanned with OS and Java DB enabled | OpenJDK CVE-2026-91403 and CVE-2026-91415 remain reported |
| Documentation | Root README rewritten; operator guidance linked and source-evidence bounds explicit | Editorial review of third-party upstream README intentionally deferred |

### Inconsistencies addressed in this integration branch

1. The root README previously stated that the authenticated UI/worker were unimplemented and combined live access permanently blocked by Zetaris login. Those statements predated later operator acceptance and were replaced with precise, scoped historical evidence and outstanding conditions.
2. The identity implementation guide still required `nbf` unconditionally although live Keycloak tokens omit it and the signed `iat` compatibility fix was tested. Clarify the optional `nbf` interpretation and that JWT temporal checks remain in force.
3. Earlier Keycloak setup guidance said `LIVE_KEYCLOAK=NOT_RUN`. Later live tests passed; retain the original guide as procedural instructions but add dated operator evidence and current remaining gates rather than silently rewriting historical instructions.
4. Generic Trivy cross-vendor severity logging was previously confused with a scanner failure. Severity source was inspected; 92 candidate findings used Red Hat severity ratings. Scanner findings themselves are not suppressed.
5. A distinct candidate image has the listed fixed CA-certificate package but unchanged OpenJDK RPM. Separate the *supported certificate mitigation* from the still-open OpenJDK advisories; do not claim vulnerability closure without independent vendor review.
6. The Docker development container's past exit code 255 is not root-caused; subsequent service recovery passed. Do not describe the cause as known.
7. README inventory includes `bridges/hmem/upstream/README.md`, a **pinned upstream reference**. This is not an original project README. It is intentionally unchanged to preserve upstream provenance and the reference hash/integrity contract. The project-owned root README is in UK English. Upstream wording must not be silently edited to meet house style.

### Engineering issues still requiring attention

- **Security:** CVE-2026-91403 is reported critical on the unchanged OpenJDK RPM, notwithstanding the system CA-store mitigation evidence; CVE-2026-91415 remains high/affected, with no fixed version supplied in the candidate Trivy report. Neither is silently waived.
- **Operational:** Keycloak is a development container. Its production TLS/reverse proxy, pinned base-image/OS lock, secrets rotation, service isolation, backup/restore, vulnerability monitoring and controlled migration have not been accepted.
- **Review process:** Independent code/security review and hosted CI were not completed. Automated local PASS does not supersede either.
- **Evidence:** Full local tests and live PKCE results are operator-reported. GitHub comments record them, but GitHub CI did not independently execute the supplied test logs.
- **Clinical:** Only synthetic malaria data have been approved for these local technical tests; human review is not clinical approval, and there is no real-world disease-surveillance validation.
- **Source provenance:** Retain vendored H-MEM README and pinned source integrity; record third-party licence/provenance review before redistribution.
- **Licensing:** Confirm an explicit licence for original AfyaEvidence code before public reuse; do not infer it from the repository being publicly accessible.

## Repeatable acceptance commands

Use Terminal 1 for the **running** identity API (if a live check needs it); Terminal 2 for tests. A full suite does not require a live provider:

```bash
cd "$HOME/afyaevidence-keycloak-live"
source "$HOME/.venvs/afyaevidence-identity/bin/activate"
source "$HOME/.nvm/nvm.sh"
nvm use 24
export PYTHONPATH="$PWD/src"
python -m pip check
python scripts/verify_identity_worker.py --fixtures
python scripts/audit_project_completeness.py --json "runtime/completeness-audit.json"
bash -n scripts/check_keycloak_java_exposure.sh
bash scripts/check_keycloak_java_exposure.sh
```

**Trust-store test limitation:** Listing certificates or observing module presence is read-only evidence, not a proof of exploitability/non-exploitability. If `keytool` is missing from the minimal image, record BLOCKED instead of installing software inside the candidate image. Do not repeat immutable synthetic review submissions.

**Release decision:** `RELEASE=BLOCKED`. A competent independent reviewer must assess CVE applicability, artefacts, controlled deployment configuration and any signed risk exception. No automatic merge or clinical/production approval.
