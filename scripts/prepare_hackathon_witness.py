#!/usr/bin/env python3
"""Create a safe, read-only demonstration witness from synthetic agent receipts.

No receipt contents or credentials are copied into the witness. A witness
records declared execution modes and receipt digests, not independently
authenticated network traces, model output or clinical conclusions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from check_hackathon_demo import assess, read

MAX_RECEIPT = 4_000_000
ALLOWED_EXPLANATIONS = {
    "reporting_artefact_supported", "mixed_reporting_artefact_and_residual",
    "testing_increase_with_stable_positivity", "unresolved_canonical_change",
    "insufficient_data", "unchanged_canonical_positives",
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def witness(fixture_path, integrated_path):
    fixture = read(fixture_path)
    integrated = read(integrated_path)
    assess(fixture, "fixture")
    assess(integrated, "integrated")
    bundle = integrated["evidence_bundle"]
    brief = integrated["candidate_brief"]
    snapshot = bundle.get("snapshot_id")
    if not isinstance(snapshot, str) or not re.fullmatch(r"ss_[0-9a-f]{64}", snapshot):
        raise ValueError("invalid_snapshot")
    explanation = brief.get("explanation")
    if not isinstance(explanation, str) or explanation not in ALLOWED_EXPLANATIONS:
        raise ValueError("unsupported_explanation")
    for key in ("model_calls", "model_call_limit", "tool_calls", "repairs"):
        if type(integrated.get(key)) is not int or integrated[key] < 0:
            raise ValueError("invalid_counts")
    if not 1 <= integrated["model_calls"] <= integrated["model_call_limit"] <= 4:
        raise ValueError("model_budget_inconsistent")
    if integrated["repairs"] > integrated["model_calls"] or integrated["tool_calls"] < 1:
        raise ValueError("tool_budget_inconsistent")
    if integrated.get("memory_pending_sync") not in (None, 0):
        raise ValueError("pending_memory_sync")
    notes = integrated.get("reference_aliases", {}).get("context", {})
    if not isinstance(notes, dict):
        raise ValueError("invalid_memory_recall")
    if len(notes) > 3:
        raise ValueError("memory_recall_limit")
    return {
        "schema": "afya-hackathon-witness-1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_receipts": {
            "fixture_sha256": sha256(fixture_path.read_bytes()).hexdigest(),
            "integrated_sha256": sha256(integrated_path.read_bytes()).hexdigest(),
        },
        "integrated": {
            "data_mode": "zetaris", "model_mode": "ollama",
            "memory_mode": "hmem_reference",
            "execution_status": "ready_for_review",
            "review_status": "awaiting_human_review",
            "execution_profile": integrated.get("execution_profile"),
            "model_calls": integrated["model_calls"],
            "model_call_limit": integrated["model_call_limit"],
            "tool_calls": integrated["tool_calls"], "repairs": integrated["repairs"],
            "explanation_category": explanation,
            "snapshot_id": snapshot,
            "recalled_context_count": len(notes),
            "memory_pending_sync": integrated.get("memory_pending_sync"),
        },
        "operator_receipt_validation": "PASS",
        "network_and_service_attestation": "NOT_INDEPENDENTLY_VERIFIED",
        "source_is_synthetic": "OPERATOR_REPORTED",
        "offline_approval": "DISABLED",
        "human_review": "REQUIRED",
        "clinical_decision": "NOT_PERFORMED",
        "production_release": "BLOCKED",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixture-receipt", required=True, type=Path)
    ap.add_argument("--integrated-receipt", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    if args.out.exists() or args.out.is_symlink():
        print("HACKATHON_WITNESS=BLOCKED_OUTPUT_EXISTS")
        return 2
    try:
        report = witness(args.fixture_receipt, args.integrated_receipt)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8") as target:
            json.dump(report, target, ensure_ascii=False, indent=2, allow_nan=False)
            target.write("\n")
        print("HACKATHON_WITNESS=PASS")
        print("HACKATHON_INTEGRATED_RECEIPT_SHA256=" + report["source_receipts"]["integrated_sha256"])
        print("HACKATHON_EXPLANATION=" + report["integrated"]["explanation_category"])
        print("HACKATHON_RECALLED_CONTEXT_COUNT=" + str(report["integrated"]["recalled_context_count"]))
        print("HACKATHON_SERVICE_ATTESTATION=NOT_INDEPENDENTLY_VERIFIED")
        print("HACKATHON_REVIEW_STATUS=awaiting_human_review")
        print("PRODUCTION_RELEASE=BLOCKED")
        print("HACKATHON_WITNESS_FILE=" + str(args.out))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeError):
        print("HACKATHON_WITNESS=BLOCKED_INVALID_EVIDENCE")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
