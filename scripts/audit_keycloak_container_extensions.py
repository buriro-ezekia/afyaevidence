#!/usr/bin/env python3
"""Read-only inventory of custom Keycloak provider JARs and theme directories.

Reads named local container filesystem through docker cp, without starting
Keycloak, accessing its realm data volume, or writing to the container.
Only presence/counts are retained; raw filenames and files are not reported.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

NAME="afyaevidence-keycloak-local"
TARGETS={"providers":"/opt/keycloak/providers","themes":"/opt/keycloak/themes"}

def docker(*args,timeout=40):
    x=subprocess.run(["docker",*args],capture_output=True,text=True,timeout=timeout)
    if x.returncode:
        raise RuntimeError("docker_"+args[0]+"_failed")
    return x.stdout

def inspect_filesystem(container, folder):
    out={"provider_jars":"NOT_VERIFIED","theme_directories":"NOT_VERIFIED",
         "custom_theme_files":"NOT_VERIFIED"}
    with tempfile.TemporaryDirectory(prefix="afya-keycloak-ext-") as d:
        root=Path(d)
        for kind,src in TARGETS.items():
            dest=root/kind
            try:
                docker("cp",f"{container}:{src}/.",str(dest),timeout=90)
            except RuntimeError:
                continue
            if kind=="providers":
                out["provider_jars"]=sum(1 for _ in dest.rglob("*.jar"))
            else:
                out["theme_directories"]=sum(1 for p in dest.iterdir() if p.is_dir())
                out["custom_theme_files"]=sum(1 for p in dest.rglob("*") if p.is_file())
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report",type=Path,required=True)
    p.add_argument("--container",default=NAME)
    a=p.parse_args()
    if a.container!=NAME:
        print("KEYCLOAK_EXTENSION_AUDIT=BLOCKED_UNEXPECTED_CONTAINER")
        return 2
    if a.report.exists():
        print("KEYCLOAK_EXTENSION_AUDIT=BLOCKED_REPORT_EXISTS")
        return 2
    try:
        data=json.loads(docker("inspect",NAME,timeout=30))
        if len(data)!=1 or data[0].get("Name")!="/"+NAME:
            raise ValueError("identity_mismatch")
        summary=inspect_filesystem(NAME,Path("."))
        summary.update({"container_name":NAME,"realm_data":"NOT_READ",
                        "image_identity":str(data[0].get("Image",""))[:80],
                        "cve_2026_91415":"OPEN","application_reachability":"NOT_VERIFIED",
                        "production_acceptance":"BLOCKED"})
        a.report.parent.mkdir(parents=True,exist_ok=True)
        with a.report.open("x",encoding="utf-8") as f:
            json.dump(summary,f,indent=2,sort_keys=True)
            f.write("\n")
        print("KEYCLOAK_EXTENSION_AUDIT=PASS" if isinstance(summary["provider_jars"],int) else
              "KEYCLOAK_EXTENSION_AUDIT=INCOMPLETE")
        for k in ("provider_jars","theme_directories","custom_theme_files"):
            print(k.upper()+"="+str(summary[k]))
        print("REALM_DATA=NOT_READ")
        print("APPLICATION_REACHABILITY=NOT_VERIFIED")
        print("CONTAINER_RELEASE=BLOCKED")
        print("REPORT="+str(a.report))
        return 0 if isinstance(summary["provider_jars"],int) and isinstance(summary["theme_directories"],int) else 2
    except (RuntimeError,ValueError,OSError,subprocess.TimeoutExpired) as exc:
        print("KEYCLOAK_EXTENSION_AUDIT=BLOCKED_"+type(exc).__name__)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
