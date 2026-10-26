#!/usr/bin/env python3
"""Export a self-contained, read-only synthetic AfyaEvidence briefcase.

This is an offline snapshot VIEW, not offline authenticated review, queued
submission, live data refresh, source mutation or cryptographic attestation.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import sys

MAX_RECEIPT = 4_000_000
MAX_TEXT = 2200

def clean(value, limit=MAX_TEXT):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("invalid_briefcase_text")
    return escape(value, quote=True)

def validate(document):
    if not isinstance(document, dict):
        raise ValueError("invalid_receipt")
    if (document.get("schema_version") != "agent-run-1" or
        document.get("execution_status") != "ready_for_review" or
        document.get("review_status") != "awaiting_human_review" or
        document.get("data_mode") != "fixture" or
        document.get("model_mode") != "scripted" or
        document.get("memory_mode") != "disabled_fixture"):
        raise ValueError("unsupported_receipt_mode")
    brief = document.get("candidate_brief")
    evidence = document.get("evidence_bundle")
    if not isinstance(brief, dict) or not isinstance(evidence, dict):
        raise ValueError("missing_evidence_or_brief")
    if (brief.get("review_status") != "awaiting_human_review" or
        brief.get("semantic_review_required") is not True or
        "approval" not in brief or brief["approval"] is not None):
        raise ValueError("human_review_boundary_invalid")
    if evidence.get("data_mode") != "fixture":
        raise ValueError("evidence_mode_mismatch")
    if not isinstance(evidence.get("snapshot_id"), str) or not evidence["snapshot_id"].startswith("ss_"):
        raise ValueError("missing_snapshot_identity")
    if not isinstance(brief.get("summary"), str) or not brief["summary"]:
        raise ValueError("invalid_summary")
    for field in ("limitations", "next_checks", "evidence_ids", "numerical_statements"):
        if not isinstance(brief.get(field), list) or len(brief[field]) > 100:
            raise ValueError("invalid_brief_field")
    available = evidence.get("evidence_records")
    if not isinstance(available, list):
        raise ValueError("missing_evidence_index")
    allowed = {record.get("evidence_id") for record in available if isinstance(record, dict)}
    if not allowed or any(ref not in allowed for ref in brief["evidence_ids"]):
        raise ValueError("invalid_evidence_citation")
    metrics = evidence.get("metrics")
    if not isinstance(metrics, list):
        raise ValueError("missing_metric_facts")
    metric_index = {m.get("metric_ref"): m for m in metrics if isinstance(m, dict)}
    if len(metric_index) != len(metrics):
        raise ValueError("duplicate_metric_reference")
    for row in brief["numerical_statements"]:
        if not isinstance(row, dict) or not isinstance(row.get("text"), str):
            raise ValueError("invalid_metric_statement")
        metric = metric_index.get(row.get("metric_ref"))
        if not isinstance(metric, dict):
            raise ValueError("unknown_metric_reference")
        value = "unavailable" if metric.get("value") is None else str(metric["value"])
        expected = (f"{metric['period']} / {metric['cohort']} / {metric['view']}: "
                    f"{metric['name']} = {value} {metric['unit']}")
        if row["text"] != expected:
            raise ValueError("metric_statement_mismatch")
        if (not isinstance(row.get("evidence_ids"), list) or
                any(item not in allowed for item in row["evidence_ids"])):
            raise ValueError("unsupported_metric_evidence")
    return brief, evidence

def render(document, digest):
    brief, evidence = validate(document)
    def items(values):
        return "".join("<li>" + clean(text, 500) + "</li>" for text in values)
    metrics = items([row["text"] for row in brief["numerical_statements"]])
    refs = items(brief["evidence_ids"])
    limitations = items(brief["limitations"])
    checks = items(brief["next_checks"])
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; connect-src 'none'">
<title>AfyaEvidence | Offline synthetic briefcase</title>
<style>
body{font:17px/1.55 system-ui,sans-serif;max-width:920px;margin:0 auto;padding:2rem;color:#172a33;background:#f8fafb}
h1,h2{line-height:1.2} h1{color:#0d4b57} section{background:white;padding:1.2rem 1.5rem;margin:1rem 0;border:1px solid #d6e3e7;border-radius:10px}
small,.muted{color:#3d5662}code{word-break:break-all}li{margin:.35rem 0}
.flag{font-weight:bold;color:#843d00} @media print{body{padding:0;background:white}section{break-inside:avoid}}
</style></head><body>
<h1>AfyaEvidence — Offline evidence briefcase</h1>
<p class="flag">SYNTHETIC DATA · SCRIPTED AGENT · READ-ONLY · AWAITING HUMAN REVIEW</p>
<p>This file opens without a network connection. It does not refresh reporting data, authenticate a reviewer, submit decisions, verify issuer signatures or provide clinical advice.</p>
<section><h2>Investigation interpretation</h2><p>""" + clean(brief["summary"]) + """</p>
<p class="muted">Explanation category: """ + clean(str(brief.get("explanation","not recorded")),100) + """</p></section>
<section><h2>Host-generated numerical statements</h2><ul>""" + metrics + """</ul></section>
<section><h2>Referenced evidence IDs</h2><ul>""" + refs + """</ul>
<p class="muted">Identifiers refer to the original immutable synthetic evidence bundle. Source records are not embedded in this portable view.</p></section>
<section><h2>Limitations</h2><ul>""" + limitations + """</ul></section>
<section><h2>Checks for a human reviewer</h2><ul>""" + checks + """</ul>
<p class="flag">No approval, rejection or clinical decision can be made in this offline file.</p></section>
<section><h2>Provenance</h2><p>Snapshot: <code>""" + clean(evidence["snapshot_id"],150) + """</code></p>
<p>Source receipt SHA-256: <code>""" + digest + """</code></p>
<p class="muted">The digest identifies the local source receipt. It is not a digital signature or independent proof of authenticity. Reopen the authenticated application to inspect the full evidence and record any human disposition.</p></section>
</body></html>
"""

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args=parser.parse_args()
    if args.output.exists():
        print("OFFLINE_BRIEFCASE=BLOCKED_OUTPUT_EXISTS")
        return 2
    try:
        if not args.receipt.is_file() or args.receipt.stat().st_size > MAX_RECEIPT:
            raise ValueError("invalid_receipt_size")
        blob=args.receipt.read_bytes()
        def unique_pairs(pairs):
            out={}
            for key,val in pairs:
                if key in out: raise ValueError("duplicate_json_key")
                out[key]=val
            return out
        doc=json.loads(blob,object_pairs_hook=unique_pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite_number")))
        page=render(doc,sha256(blob).hexdigest())
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open("x",encoding="utf-8",newline="\n") as f:
            f.write(page)
        print("OFFLINE_BRIEFCASE=PASS")
        print("MODE=synthetic_scripted_read_only")
        print("NETWORK_DEPENDENCIES=NONE")
        print("OFFLINE_REVIEW_SUBMISSION=DISABLED")
        print("HUMAN_REVIEW=REQUIRED")
        print("OFFLINE_OUTPUT="+str(args.output))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,RecursionError):
        print("OFFLINE_BRIEFCASE=BLOCKED_INVALID_OR_UNSUPPORTED_RECEIPT")
        return 2

if __name__=="__main__":
    raise SystemExit(main())
