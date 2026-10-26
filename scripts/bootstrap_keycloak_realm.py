#!/usr/bin/env python3
"""Idempotent local-only Keycloak realm/client/role bootstrap (no user credentials printed).

Requires pre-existing development container from start_keycloak_local.sh.
Does not touch AfyaEvidence databases, real accounts, or PR #3.
"""
import json
import os
from pathlib import Path
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, HTTPSHandler, Request, build_opener

BASE = "https://localhost:8443"
ROOT = Path.home()/".local/state/afyaevidence-keycloak-local"
REALM = "afya-local"
RESOURCE = "afya-review-introspection"
LOGIN = "afya-human-login"

def stop(code):
    print("KEYCLOAK_BOOTSTRAP=BLOCKED: "+code)
    raise SystemExit(2)

def request(opener, method, path, token=None, body=None, form=False):
    headers = {"Accept":"application/json"}
    if token:
        headers["Authorization"]="Bearer "+token
    if body is not None:
        if form:
            raw=urlencode(body).encode()
            headers["Content-Type"]="application/x-www-form-urlencoded"
        else:
            raw=json.dumps(body).encode()
            headers["Content-Type"]="application/json"
    else: raw=None
    req=Request(BASE+path,data=raw,headers=headers,method=method)
    try:
        with opener.open(req,timeout=12) as resp:
            data=resp.read(256001)
            if len(data)>256000: stop("provider response too large")
            return resp.status,(json.loads(data) if data else None)
    except HTTPError as e:
        if e.code==404: return 404,None
        if e.code==409: return 409,None
        stop("Keycloak rejected "+method+" "+path.split("?")[0]+" (HTTP "+str(e.code)+")")
    except (URLError,ValueError,OSError):
        stop("trusted HTTPS request failed")

def main():
    cert=ROOT/"tls/tls.crt"
    env=ROOT/"bootstrap.env"
    if not cert.is_file() or not env.is_file():
        stop("missing private HTTPS bootstrap material")
    cfg={}
    for line in env.read_text().splitlines():
        if "=" in line:
            k,v=line.split("=",1)
            if k in ("KC_BOOTSTRAP_ADMIN_USERNAME","KC_BOOTSTRAP_ADMIN_PASSWORD"):
                cfg[k]=v
    if not cfg.get("KC_BOOTSTRAP_ADMIN_USERNAME") or not cfg.get("KC_BOOTSTRAP_ADMIN_PASSWORD"):
        stop("bootstrap admin credentials missing")
    context=ssl.create_default_context(cafile=str(cert))
    opener=build_opener(ProxyHandler({}),HTTPSHandler(context=context))
    _, token_doc=request(opener,"POST","/realms/master/protocol/openid-connect/token",
        body={"grant_type":"password","client_id":"admin-cli",
              "username":cfg["KC_BOOTSTRAP_ADMIN_USERNAME"],
              "password":cfg["KC_BOOTSTRAP_ADMIN_PASSWORD"]},form=True)
    token=(token_doc or {}).get("access_token")
    if not isinstance(token,str): stop("admin authentication unavailable")
    status,_=request(opener,"GET","/admin/realms/"+REALM,token)
    if status==404:
        request(opener,"POST","/admin/realms",token,
                {"realm":REALM,"enabled":True,"accessTokenLifespan":300})
        print("KEYCLOAK_REALM=CREATED")
    else:
        print("KEYCLOAK_REALM=EXISTS")
    for cid, opts in (
        (RESOURCE,{"publicClient":False,"clientAuthenticatorType":"client-secret",
                   "standardFlowEnabled":False,"directAccessGrantsEnabled":False,
                   "serviceAccountsEnabled":False,"fullScopeAllowed":False}),
        (LOGIN,{"publicClient":True,"standardFlowEnabled":True,"implicitFlowEnabled":False,
                "directAccessGrantsEnabled":False,"serviceAccountsEnabled":False,
                "fullScopeAllowed":False,
                "redirectUris":["http://127.0.0.1:8765/callback"],
                "webOrigins":[],"attributes":{"pkce.code.challenge.method":"S256",
                    "use.jwks.url":"false"}})):
        status, clients=request(opener,"GET",f"/admin/realms/{REALM}/clients?clientId={cid}",token)
        if not isinstance(clients,list):stop("client lookup failed")
        if clients:
            print("KEYCLOAK_CLIENT_"+cid.upper().replace("-","_")+"=EXISTS")
        else:
            request(opener,"POST",f"/admin/realms/{REALM}/clients",token,
                    {"clientId":cid,"enabled":True,"protocol":"openid-connect",**opts})
            print("KEYCLOAK_CLIENT_"+cid.upper().replace("-","_")+"=CREATED")
    for role in ("viewer","reviewer","administrator"):
        status,_=request(opener,"GET",f"/admin/realms/{REALM}/roles/{role}",token)
        if status==404:
            request(opener,"POST",f"/admin/realms/{REALM}/roles",token,
                    {"name":role,"description":"AfyaEvidence test-only "+role+" role"})
            print("KEYCLOAK_ROLE_"+role.upper()+"=CREATED")
        else:
            print("KEYCLOAK_ROLE_"+role.upper()+"=EXISTS")
    print("KEYCLOAK_BOOTSTRAP=PASS")
    print("KEYCLOAK_ROLE_MAPPER=NOT_CONFIGURED")
    print("KEYCLOAK_TOKEN_CLAIMS=NOT_TESTED")
    print("KEYCLOAK_HUMAN_ACCOUNTS=NOT_CREATED")
    print("LIVE_USER_AUTH=NOT_TESTED")
    print("NOTE=Configure at+jwt, audience and flat roles mappers in Keycloak Admin UI")
    return 0

if __name__=="__main__":
    sys.exit(main())
