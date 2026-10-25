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
