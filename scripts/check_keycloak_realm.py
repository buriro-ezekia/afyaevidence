#!/usr/bin/env python3
"""Read-only HTTPS discovery for the isolated Keycloak AfyaEvidence realm."""
import json
import os
import ssl
import sys
from pathlib import Path
from urllib.request import ProxyHandler, HTTPSHandler, build_opener
from urllib.parse import urlsplit

EXPECTED = "https://localhost:8443/realms/afya-local"
CA = Path.home()/".local/state/afyaevidence-keycloak-local/tls/tls.crt"

def main():
    if not CA.is_file():
        print("KEYCLOAK_REALM_DISCOVERY=BLOCKED: trusted local certificate missing")
        return 2
    context = ssl.create_default_context(cafile=str(CA))
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context))
    try:
        with opener.open(EXPECTED+"/.well-known/openid-configuration",timeout=7) as response:
            if response.status != 200 or response.headers.get_content_type() != "application/json":
                raise ValueError("unexpected_http_response")
            blob=response.read(65537)
        if len(blob)>65536:
            raise ValueError("discovery_too_large")
        doc=json.loads(blob)
        for field in ("issuer","jwks_uri","introspection_endpoint","authorization_endpoint","token_endpoint"):
            value=doc.get(field)
            if not isinstance(value,str) or not value.startswith(EXPECTED+"/") and not (field=="issuer" and value==EXPECTED):
                raise ValueError("invalid_"+field)
            parsed=urlsplit(value)
            if parsed.scheme!="https" or parsed.hostname!="localhost" or parsed.port!=8443:
                raise ValueError("invalid_endpoint")
        if doc["issuer"]!=EXPECTED:
            raise ValueError("issuer_mismatch")
        print("KEYCLOAK_REALM_DISCOVERY=PASS")
        print("KEYCLOAK_ISSUER_MATCH=PASS")
        print("KEYCLOAK_JWKS_ENDPOINT=PASS")
        print("KEYCLOAK_INTROSPECTION_ENDPOINT=PASS")
        print("LIVE_USER_AUTH=NOT_TESTED")
        return 0
    except Exception:
        print("KEYCLOAK_REALM_DISCOVERY=BLOCKED: HTTPS endpoint or issuer not ready")
        return 2

if __name__=="__main__":
    sys.exit(main())
