# CVE-2026-91415 — Keycloak 26.8.1 OpenJDK 2D applicability assessment

**Date:** 25 October 2026. **Decision:** `OPEN`; container production approval remains **BLOCKED**.

This assessment distinguishes a vulnerable **installed Java package**, a Java 2D
**module**, a Keycloak **image-generation call path**, and a proven **exploit
path**. Those are different levels of evidence. No exploit attempt or fuzzing
against the running realm was undertaken.

## Vendor advisory and affected software

Red Hat marks CVE-2026-91415 **Important** with CVSS v3 4.8 and reports an
OpenJDK 2D vulnerability associated with font rendering (Red Hat bug 2557443).
Oracle's October 2026 advisory characterises the 2D component as potentially
reachable through APIs that process untrusted data; the exact vulnerable method
and font-input preconditions have **not** been demonstrated in this deployment.

The pinned candidate Keycloak image uses RHEL 9
`java-21-openjdk-headless 1:21.0.12.1.1-1.2.el9`. Trivy (Red Hat severity
source) reports CVE-2026-91415 **HIGH**, status **affected**, with no fixed
package version listed in the operator's candidate report. Being labelled
*headless* does not eliminate `java.desktop`: the operator verified
`JAVA_DESKTOP_MODULE=PRESENT`.

## Source-traced application path

Inspection of **Keycloak tag 26.8.1**, rather than a different upstream tag,
identified the following application sequence:

1. `services/src/main/java/org/keycloak/utils/TotpUtils.java`:
   `qrCode(...)` derives an OTP-provisioning URI from the configured realm
   name and user account, then invokes `QRCodeUtils.encodeAsQRString`
   with **fixed width and height of 246**.
2. `services/src/main/java/org/keycloak/utils/QRCodeUtils.java`:
   `encodeAsQRBytes` invokes ZXing `QRCodeWriter` and
   `com.google.zxing.client.j2se.MatrixToImageWriter.writeToStream`
   to generate PNG image bytes. `encodeAsQRString` Base64-encodes them.
3. The dependency on ZXing's Java SE image writer is a substantive reason to
   check Java imaging functionality in the exact pinned candidate, rather
   than assuming Keycloak never touches Java 2D.

**Crucial qualification:** QR encoding is not proof of vulnerable **font
rendering**. The traced path uses fixed image dimensions and an OTP URI, not
an identified attacker-supplied font. Its exposure depends on the configured
OTP flow, authenticated sessions, realm permissions and any untrusted
parameters that actually reach image/font APIs. No such exploit path has
been demonstrated here.

## Threat-model table

| Possible source of untrusted input | Observed evidence | Security conclusion |
| --- | --- | --- |
| OTP enrolment, realm display name and username | Keycloak tag 26.8.1 source reaches ZXing PNG image generation | Some request/account/realm-derived content reaches image generation; font-rendering exploitability **not established** |
| User profile text fields | Profile properties are configurable in Keycloak; no vulnerable 2D call path established here | Needs deployment-specific route and code tracing |
| Custom identity providers or extensions | Operator's installed provider JARs have not been inventoried | **Not verified**; may extend processing surface |
| Custom themes/static image resources | Keycloak supports themes, but the runtime access path was not independently audited | **Not verified**; static file serving does not alone imply Java image decoding |
| Arbitrary image or font upload | No such public endpoint has been established in this deployed realm | Do not claim absent globally without route/configuration inspection |
| OpenJDK installed Java desktop module | Present in pinned candidate | Vulnerable code potentially present, not proof of reachable invocation |

## Pinned-image static inventory

The companion command
`python scripts/audit_keycloak_java2d_static.py --report runtime/security/keycloak-java2d-static.json`
performs an **offline** inspection. It verifies the exact image RepoDigest,
recognised manifest/configuration ID and `linux/amd64` platform. It creates
but **never starts** an ephemeral container to copy the shipped Keycloak
`lib/lib/main`, `lib/app` and `providers` directories into an automatic
temporary location; then removes the ephemeral container. No live realm
volume or credential is mounted and no network call is needed.

Host Python inspects `.class` bytes in installed JARs for constant-pool-like
markers `java/awt/`, `java/awt/font/`, `javax/imageio/`,
`sun/font/` and `sun/java2d/`. It prints counts and writes an explicit
JSON report under ignored `runtime/`. The report never claims
reachability merely because byte references were found.

**Limitations:** This is a **string-marker heuristic**, not a bytecode
call-graph, taint analysis, proof of class loading, exploit reproduction or
complete inventory of native/font libraries. Reflection, dynamically loaded
classes, optional features and missing JARs can evade it. Positive results
require class/source inspection; negative results do not prove safety.
Unscanned oversized classes or unreadable JARs block a complete static
inventory rather than being hidden. The operator must run this script on
the exact candidate before its output can enter the evidence register.

## Operator static-inventory result — 25 October 2026

The operator executed the pinned candidate static inventory and reported
`JAVA2D_STATIC_INVENTORY=PASS`. The scan examined **355 JAR archives**
containing **69,885 Java class files** and found **69 class files** with
Java AWT, ImageIO, font or Java 2D byte-string indicators. The local JSON
report is `runtime/security/keycloak-java2d-static.json`, and remains
outside Git. The report's per-JAR and per-class matching evidence has **not
yet been reviewed**; source-level and runtime reachability analysis is
therefore not complete.

The tool itself reported `APPLICATION_REACHABILITY=NOT_VERIFIED`,
`CVE_2026_91415=OPEN` and `CONTAINER_RELEASE=BLOCKED`.
This is a **successful inventory**, not confirmation that the exact vulnerable
font-rendering operation is present in a reachable API. Review the
individual matched classes and any installed extension JARs before making
an applicability judgement. Preserve the image and realm in place.

## Per-library inventory triage — 25 October 2026

The operator inspected all **69 matching classes** from the complete static
inventory. They occur in **11 JARs**, all under `main`, with no matches
reported under application/provider sections. This is not proof that those
sections contain no extensions, and it is not a full call graph.

| JAR / functional area | Matching classes | Priority / interpretation |
| --- | ---: | --- |
| `com.google.zxing.javase-3.4.0.jar` | 6 | **High:** includes `MatrixToImageWriter`, directly used by OTP QR-code generation |
| `org.locationtech.jts.jts-core-1.19.0.jar` | 19 | **High:** contains `FontGlyphReader`, the **sole `JAVA_FONT`** match |
| `com.sun.xml.messaging.saaj.saaj-impl-2.0.1.jar` | 3 | SOAP GIF/JPEG image handling; untrusted input path unverified |
| `org.eclipse.angus.angus-mail-2.0.5.jar` | 2 | Mail GIF/JPEG content handling; reachability unverified |
| `org.glassfish.jaxb.jaxb-runtime-4.0.9.jar` | 4 | Data binding and image conversion; reachability unverified |
| `io.quarkus.quarkus-core-3.40.1.jar` | 5 | Runtime/native-image substitution classes; not evidence of a reachable endpoint |
| `org.jgroups.jgroups-5.5.5.Final.jar` | 20 | Mostly demonstration/graphical utility classes |
| `org.jboss.narayana.jta.narayana-jta-7.3.4.Final.jar` | 6 | Transaction-monitor graphical utilities |
| `net.java.dev.jna.jna-5.8.0.jar` | 2 | AWT references from native compatibility |
| `com.h2database.h2-2.4.240.jar` | 1 | GUI console |
| `org.postgresql.postgresql-42.7.13.jar` | 1 | AWT-compatible geometric object |

**Evidence from dependency implementation:** ZXing's tagged `3.4.0`
`MatrixToImageWriter` creates `java.awt.image.BufferedImage`, sets pixels
and writes with `javax.imageio.ImageIO.write`. That demonstrates
image processing, but no explicit font-glyph rendering in this method.
JTS `1.19.0` `FontGlyphReader` provides APIs converting text in
`java.awt.Font` into geometry; it is an installed font-processing
facility, but **no Keycloak caller has been identified**. Neither result
identifies the precise vulnerable OpenJDK method.

The underlying vulnerability concerns OpenJDK 2D font rendering;
installation of graphics APIs is a sufficient **investigation trigger**,
not proof of an external exploit route. The narrow next analysis is to
identify reverse references to `FontGlyphReader` and other known font
APIs, inspect Keycloak's user-controllable endpoints and configuration,
and obtain vendor-specific affected-method/patch evidence. Do not
silence CVE-2026-91415 or downgrade it because most matches are
utility/demo classes.

Additional code/API references:
- https://github.com/zxing/zxing/blob/zxing-3.4.0/javase/src/main/java/com/google/zxing/client/j2se/MatrixToImageWriter.java
- https://javadoc.io/static/org.locationtech.jts/jts-core/1.19.0/org/locationtech/jts/awt/FontGlyphReader.html

## Focused reverse-reference verification — locally completed, CVE still open

The follow-up script `scripts/audit_keycloak_java2d_reverse_refs.py`
reads JVM class-file constant-pool UTF-8 entries from the exact pinned
Keycloak image. It distinguishes references to
`org/locationtech/jts/awt/FontGlyphReader`,
`com/google/zxing/client/j2se/MatrixToImageWriter`,
`java/awt/Font`, `java/awt/font/`, `java/awt/Graphics2D`
and `javax/imageio/ImageIO`. Results include the referring
class, JAR and section (`main`, `app` or `providers`).
The command uses an unstarted temporary container, never the running
Keycloak realm, and saves a new report under ignored `runtime/`.

```bash
python -m unittest discover -s tests -p 'test_keycloak_java2d_reverse_refs.py' -v
python scripts/audit_keycloak_java2d_reverse_refs.py \\
  --report runtime/security/keycloak-java2d-references.json
```

This is **structural reference evidence**, not a method-invocation
call graph, a proof of remote reachability or a vulnerability test.
A reference from a library to its own class or a graphics API is
not evidence that a Keycloak request exercises that code. The
result must be inspected by class owner and call path, ideally alongside
an exact vendor patch or affected-method description.
The operator has completed the candidate reverse-reference scan; the focused
four-test outcome was not included in the supplied output. Preserve the existing
JSON reports and do not overwrite their evidential record.

## Candidate reverse-reference results — 25 October 2026

The operator reported `JAVA2D_REVERSE_AUDIT=PASS` for the same pinned
candidate: **355 JARs**, **69,885 class files** inspected, with **17
reference-bearing classes**. All 17 appeared in `main`; none were reported
in `app` or `providers`. Counts of references are **not mutually
exclusive**: `JTS_FONT_GLYPH=1`, `ZXING_MATRIX_IMAGE=3`,
`JAVA_AWT_FONT=8`, `JAVA_FONT_PACKAGE=1`,
`JAVA2D_GRAPHICS=4`, `JAVA_IMAGEIO=6`.

The separate print command filtered out records that matched only
`JAVA_IMAGEIO`. It printed **15 classes rather than all 17**.
The two omitted entries have now been identified from the preserved local
JSON report as ZXing Java SE 3.4.0 `DecodeWorker.class` and
`ImageReader.class`, both with only `JAVA_IMAGEIO` references. All **17**
matched class records are accounted for; there are no unexplained count
differences. Neither class alone demonstrates font rendering or a remotely
reachable vulnerability.

### Reachability observations

- The **single** `JTS_FONT_GLYPH` hit was
  `org/locationtech/jts/awt/FontGlyphReader.class` itself. This is not
  evidence that a separate Keycloak class calls that method. There was no
  independent reverse-reference to `FontGlyphReader` in the supplied
  records. A constant-pool reference can be a self-reference, not a
  call-site; reflection, native calls and dynamic loading remain outside
  this method.
- Among the **three** `ZXING_MATRIX_IMAGE` hits, one belongs to
  `org/keycloak/utils/QRCodeUtils.class`, directly corroborating the
  tagged Keycloak OTP QR-code generation path. The other two are within
  the ZXing library itself. The writer constructs a `BufferedImage`,
  sets its pixels and invokes `ImageIO.write`; the documented path
  does not establish untrusted font rendering.
- AWT font references in JGroups graphical demonstrations and H2's GUI
  console establish included **utility classes**, not reachable
  authentication endpoints. SOAP/JAXB ImageIO handlers similarly warrant
  source review only if an application endpoint or integration exercises
  them.
- **No matches in `app` and `providers`** means no target references
  were detected there by this particular scanner, not a proof that custom
  extensions are absent or that all possible call paths have been ruled out.

### Assurance and release implications

The evidence narrows the likely surface: server-side image generation is
real and traceable, whereas **an independent caller of JTS's
`FontGlyphReader` is not demonstrated**. This must not be inverted into
proof of non-applicability. The scanner performs constant-pool string
inspection; it neither proves method invocation nor tracks user-controlled
input to the OpenJDK method implicated by CVE-2026-91415.
**APPLICATION_REACHABILITY=NOT_VERIFIED**, **CVE_2026_91415=OPEN**
and **CONTAINER_RELEASE=BLOCKED** remain the correct outcomes.

The next evidential priorities are the two omitted ImageIO-only records,
confirmation of the actual realm's OTP and provider/theme configuration
without exposing credentials or user data, and vendor disclosure of
affected OpenJDK call sites or a supported patched build. Any
risk exception requires independent security sign-off.

## RHEL 9 vendor fix status and local realm configuration — 25 October 2026

A fresh check of [Red Hat's CVE-2026-91415 database](https://access.redhat.com/security/cve/cve-2026-91415)
identifies the Java 2D vulnerability as **Important**, CVSS v3
**4.8**. The published affected-packages view lists OpenJDK builds as
affected with no published erratum for the displayed entries. The
candidate image's Trivy record continues to show RHEL 9
`java-21-openjdk-headless 1:21.0.12.1.1-1.2.el9`, **HIGH /
affected**, without a fixed version. A live RHEL package repository
query or vendor-specific update confirmation has **not** been executed
on the candidate; therefore this check does not prove that no future
package update could exist.

For CVE-2026-91403, Red Hat currently describes RHEL 9 OpenJDK as
**under investigation** and says its non-portable RPMs consume the
fixed system `ca-certificates` store. The candidate package/trust
evidence already supports the mitigation hypothesis, not security
sign-off. Preserve both advisories individually.

### Realm configuration and extensions still requiring local evidence

Created `scripts/audit_keycloak_realm_exposure.py`, which reads
**local JSON exports**, not live Keycloak, and emits only sanitised
counts/statuses for OTP required actions, browser-flow executions,
selected theme presence and provider-component count. It strips
usernames, IDs, credentials, realm names, component names, theme names
and any other raw configuration from its output. Absent source inputs
are **NOT_VERIFIED**, not silently assumed disabled. It does not
modify the realm.

Usage after an authorised administrator has saved JSON files in the
ignored private `runtime/security/realm-input/` directory:

```bash
python scripts/audit_keycloak_realm_exposure.py \\
  --realm runtime/security/realm-input/realm.json \\
  --required-actions runtime/security/realm-input/required-actions.json \\
  --executions runtime/security/realm-input/browser-executions.json \\
  --components runtime/security/realm-input/components.json \\
  --report runtime/security/keycloak-realm-exposure.json
```

Export only the specific realm settings, **never user lists or tokens**.
The optional inputs must reflect the actual `afya-local` realm and its
selected browser authentication flow. Collecting those files is an
authorised operator action; do not commit or paste their contents.
The script can run with only `--realm` and `--report`, but then
prints that other categories are `NOT_VERIFIED`.

Realm flow and theme configuration cannot independently prove font
processing reachability. An enabled OTP action indicates a possible
QR-code journey; it does not establish an externally reachable Java
font-rendering exploit. A disabled OTP action would not clear installed
OpenJDK vulnerability exposure through other endpoints or extensions.

### Direct read-only admin API check (optional)

The alternative `scripts/audit_keycloak_live_realm.py` queries **only**
the local HTTPS Keycloak Admin REST API's realm configuration, selected
browser-flow executions, required actions and provider components.
It takes an **authorised administrator access token via hidden input**
(no password grant, no token saved to disk), enforces the explicitly
trusted local certificate, does not follow redirects and never writes
raw provider/realm data. Only a sanitised local JSON summary is saved.

Terminal 1 can remain unused by AfyaEvidence. If the Keycloak development
container is stopped, start **that existing container only**, preserving
its volume and configuration; do not create a new realm or reset users.

```bash
python scripts/audit_keycloak_live_realm.py \\
  --ca-cert "$HOME/.local/state/afyaevidence-keycloak-local/tls/tls.crt" \\
  --report runtime/security/keycloak-live-realm-audit.json
```

The script requires an authorised **admin API access token**, which
must be obtained through an approved administrator session. Do not paste
the token into chat, put it in Git, or copy the raw API payloads.
A token for the AfyaEvidence viewer/reviewer roles is insufficient.

The output will report OTP enablement, browser-flow execution counts,
theme presence and provider-component counts, while keeping raw names
and configuration private. **Neither enabled nor disabled OTP by itself
proves CVE-2026-91415 reachability or non-applicability.** If the
admin API cannot be accessed, the security evidence is explicitly
`NOT_VERIFIED`, not invented.

### Stopped-container extension and theme inventory

`scripts/audit_keycloak_container_extensions.py` inspects only
`/opt/keycloak/providers` and `/opt/keycloak/themes` in the **existing**
`afyaevidence-keycloak-local` container. It works even when that container
is stopped. Docker copies these two directories to a short-lived local
temporary directory; the script counts provider JARs, theme directories and
theme files, then deletes the temporary copy. It never reads
`/opt/keycloak/data`, mounts the realm volume, starts the container or
makes a network request. Names, themes and provider byte content are
not included in the final JSON report.

```bash
python scripts/audit_keycloak_container_extensions.py \\
  --report runtime/security/keycloak-extension-inventory.json
```

This reports **presence**, not which extension classes are invoked.
Container image built-in providers may not reside under `providers/`.
If the provider or theme directory cannot be read, the result stays
`NOT_VERIFIED`, rather than being silently reported as empty.

The live realm administrator audit (described above) checks configured
OTP required actions, the browser-flow steps and theme settings, but
does **not** establish all nested subflows or actual browser-route
reachability. It requires an authorised admin token and running
Keycloak. Do not claim these checks were performed until the operator
supplies their results; no admin credentials should be shared.

### Admin API HTTP failure diagnostics — 25 October 2026

The operator received `KEYCLOAK_LIVE_REALM_AUDIT=BLOCKED_HTTPError`.
The previous audit intentionally hid HTTP response details, but also
concealed the safe status code and which read-only endpoint rejected the
request. The updated script now reports `FAILED_STAGE`, `HTTP_STATUS`
and a short diagnosis, while never printing the token, raw URL,
response headers or body.

- `401` means the bearer token was rejected or expired. An AfyaEvidence
  application-role token is not a Keycloak realm administrator token.
- `403` means the authenticated principal lacks permission for the
  indicated Admin REST endpoint. Use an authorised Keycloak admin
  identity; do not broaden viewer/reviewer permissions just to pass a test.
- `404` means the selected realm, browser-flow reference or endpoint
  must be verified. Avoid changing the realm until the request is
  understood.
- Other HTTP codes (including redirects) remain BLOCKED, not PASS.

The failure does **not** establish anything about OTP enablement, themes,
providers or CVE-2026-91415 reachability. The operator should fetch the
updated branch and run the offline HTTP error tests, then rerun the
audit with an appropriately authorised short-lived admin token. Keep
tokens and raw realm responses private. This procedure does not require
starting the AfyaEvidence review API.

### Repeated HTTP 401 and administrator token preflight — 25 October 2026

The operator confirmed a working browser Admin Console request to
`GET /admin/realms/afya-local` (**HTTP 200**) but the Python
read-only audit repeatedly received **HTTP 401** at its initial
`realm` stage. A previous privately decoded access token had
`TOKEN_EXPIRED=True`, with issuer realm `master`. The browser's
separate successful request does not establish that the **same**
unexpired bearer credential was supplied to Python.

The live audit now performs a **local, non-verifying token preflight**
before any HTTPS request. It displays only whether the JWT is expired
or malformed, the expected local issuer realm and remaining seconds.
It does **not** print or persist token bytes or trust decoded JWT
claims as verified identity; Keycloak still determines authentication
by its Admin REST response. An expired token produces a clear
`BLOCKED_TOKEN_PREFLIGHT` without an unnecessary HTTP call. A
token with unexpired claimed `exp` may still be rejected due to
signature, audience, revocation or administrative-session conditions.

Retain Keycloak's short-lived tokens. Use a fresh authorised admin
**access token**, not an ID/refresh token or the AfyaEvidence application
`administrator` account. Do not extend token lifetime or expand
realm permissions solely to make the audit pass. All realm exposure
findings remain `NOT_VERIFIED` until the read-only API succeeds.

### Independent release decision

A human security reviewer must evaluate exact vendor patch guidance,
configured enabled flows, provider JARs, custom themes, library call
paths and the specific OpenJDK font-rendering preconditions. In the
absence of a supported fixed package or a fully evidenced
non-applicability decision, **CVE-2026-91415 stays OPEN and production
deployment remains BLOCKED**. Do not disable the project's authentication
protections merely to avoid triggering image generation.

## Release acceptance and targeted next checks

1. Execute the static inventory on the *pinned candidate*. Identify which
   shipped classes invoke Java image/font APIs; inspect the highest-priority
   Keycloak server/resource classes and any installed provider JARs.
2. Confirm whether the actual `afya-local` realm enables OTP enrolment and
   whether the implicated methods receive fonts or graphics from untrusted
   sources. Do not post the private realm export or user records.
3. Consult Keycloak and Red Hat on the specific OpenJDK 2D advisory and any
   RHEL 9 erratum/fixed package. Evaluate a separately pinned patched
   candidate if available, with an independent scanner result.
4. Obtain independent code/security review of the affected call path and
   configured extension/theme inventory. The existing local PKCE, identity,
   revocation and role checks support **functionality**, not safety of the
   font-rendering component.
5. Re-run production-specific TLS, systemd isolation, resource limits,
   trusted-image supply chain and rollback drills on disposable copies. Never
   mutate the historical accepted review or active development realm to run
   these checks.

**Conclusion:** The Java desktop module is present, and there is a genuine
Keycloak server-side PNG image-generation path through ZXing. Neither finding
demonstrates CVE-2026-91415's **specific font-rendering** preconditions.
Consequently, *not affected*, *mitigated*, *fixed* and *production approved*
would all be unjustified classifications today. Maintain
`CVE_2026_91415=OPEN` and `CONTAINER_RELEASE=BLOCKED`.

## Primary references

- Red Hat advisory: https://access.redhat.com/security/cve/cve-2026-91415
- Red Hat bug: https://bugzilla.redhat.com/show_bug.cgi?id=2557443
- Oracle October 2026 Critical Patch Update:
  https://www.oracle.com/security-alerts/cpuoct2026.html
- Keycloak exact tag, TotpUtils:
  https://github.com/keycloak/keycloak/blob/26.8.1/services/src/main/java/org/keycloak/utils/TotpUtils.java
- Keycloak exact tag, QRCodeUtils:
  https://github.com/keycloak/keycloak/blob/26.8.1/services/src/main/java/org/keycloak/utils/QRCodeUtils.java
- Keycloak container directory layout:
  https://www.keycloak.org/server/directory-structure
