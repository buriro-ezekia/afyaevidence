#!/usr/bin/env python3
"""Assess a hackathon demonstration without touching live services or secrets.

Reads existing agent receipts and checks source, model and memory modes.
This check never queries Zetaris, calls Ollama, writes H-MEM or approves
an investigation. It cannot authenticate claims inside a local receipt.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

MAX_FILE = 4_000_000


def read(path):
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        raise ValueError("missing_or_oversized_receipt")
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate_json_key")
            out[key] = value
        return out
    return json.loads(path.read_bytes(), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite_json")))


def assess(document, expected):
    if not isinstance(document, dict):
        raise ValueError("invalid_receipt")
    if (document.get("schema_version") != "agent-run-1" or
        document.get("execution_status") != "ready_for_review"):
        raise ValueError("agent_not_ready")
    if document.get("review_status") != "awaiting_human_review":
        raise ValueError("review_boundary_missing")
    brief = document.get("candidate_brief")
    if (not isinstance(brief, dict) or brief.get("approval") is not None or
        brief.get("semantic_review_required") is not True or
        brief.get("review_status") != "awaiting_human_review"):
        raise ValueError("human_review_boundary_failed")
    bundle = document.get("evidence_bundle")
    if not isinstance(bundle, dict) or not bundle.get("snapshot_id"):
        raise ValueError("evidence_bundle_missing")
    if not isinstance(brief.get("evidence_ids"), list) or not brief["evidence_ids"]:
        raise ValueError("uncited_brief")
    if expected == "fixture":
        required = {"data_mode": "fixture", "model_mode": "scripted",
                    "memory_mode": "disabled_fixture"}
    elif expected == "integrated":
        required = {"data_mode": "zetaris", "model_mode": "ollama",
                    "memory_mode": "hmem_reference"}
    else:
        raise ValueError("unsupported_expected_mode")
    if any(document.get(key) != value for key, value in required.items()):
        raise ValueError("mode_mismatch")
    if bundle.get("data_mode") != required["data_mode"]:
        raise ValueError("bundle_mode_mismatch")
    return {"model_calls": document.get("model_calls"),
            "tool_calls": document.get("tool_calls"),
            "review": brief["review_status"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fixture-receipt", type=Path, required=True)
    p.add_argument("--integrated-receipt", type=Path,
                   help="Optional successful real Zetaris/Ollama/H-MEM agent receipt")
    args = p.parse_args()
    try:
        assess(read(args.fixture_receipt), "fixture")
        print("HACKATHON_FIXTURE_AGENT=PASS")
        print("HACKATHON_SYNTHETIC_EVIDENCE=PASS")
        print("HACKATHON_HUMAN_REVIEW_BOUNDARY=PASS")
        if args.integrated_receipt is None:
            print("HACKATHON_ZETARIS_OLLAMA_HMEM=NOT_VERIFIED")
            print("HACKATHON_DEMO_GATE=INCOMPLETE")
            return 3
        assess(read(args.integrated_receipt), "integrated")
        print("HACKATHON_INTEGRATED_RECEIPT=PASS")
        print("HACKATHON_INTEGRATED_SERVICES=OPERATOR_RECEIPT_NOT_INDEPENDENTLY_ATTESTED")
        print("HACKATHON_METERLESS_REFERENCE_READS=CHECK_TRACE_AND_HMEM_SMOKE")
        print("HACKATHON_HUMAN_REVIEW_BOUNDARY=PASS")
        print("HACKATHON_DEMO_GATE=READY_FOR_OPERATOR_WITNESS")
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError):
        print("HACKATHON_DEMO_GATE=BLOCKED_INVALID_OR_FAILED_RECEIPT")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
