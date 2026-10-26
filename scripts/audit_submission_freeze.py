#!/usr/bin/env python3
"""Read-only source/receipt freeze audit for a synthetic hackathon submission.

Output is an exclusive new file under runtime/. No secrets, raw source
records or entire agent receipts are included. An earlier CI commit is
not represented as validation of this frozen code.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys

FROZEN_SOURCE_SHA = "80fbb9fd52c2ecc0b3f987e476e3908c6fbc4a71"
INTEGRATED_SHA = "3befe3839b2988398a30ffc786d8f4f4bc6a77274dc9be637aa6eb2e7a813af1"
CI_FIRST_GREEN_SHA = "391237a992a93291771c57e0b09ab3b4d00d2178"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
ROOT = Path(__file__).resolve().parents[1]


def valid_git_commit_sha(value):
    """Accept full SHA-1 or SHA-256 Git object IDs; never abbreviated IDs."""
    return isinstance(value, str) and GIT_SHA.fullmatch(value) is not None


def git(*args):
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                            text=True, timeout=12, check=False)
    if result.returncode:
        raise ValueError("git_state_unavailable")
    return result.stdout.strip()


def validate(witness, receipt, *, expected_sha=INTEGRATED_SHA):
    if not isinstance(witness, dict) or witness.get("schema") != "afya-hackathon-witness-1":
        raise ValueError("invalid_witness_schema")
    source = witness.get("source_receipts")
    integrated = witness.get("integrated")
    if not isinstance(source, dict) or not isinstance(integrated, dict):
        raise ValueError("invalid_witness_body")
    digest = sha256(receipt).hexdigest()
    if source.get("integrated_sha256") != digest or digest != expected_sha:
        raise ValueError("integrated_receipt_digest_mismatch")
    if (integrated.get("data_mode") != "zetaris" or
        integrated.get("model_mode") != "ollama" or
        integrated.get("memory_mode") != "hmem_reference" or
        integrated.get("execution_status") != "ready_for_review" or
        integrated.get("review_status") != "awaiting_human_review" or
        integrated.get("explanation_category") != "reporting_artefact_supported" or
        integrated.get("recalled_context_count") != 0 or
        integrated.get("memory_pending_sync") not in (None, 0) or
        witness.get("human_review") != "REQUIRED" or
        witness.get("production_release") != "BLOCKED" or
        witness.get("network_and_service_attestation") != "NOT_INDEPENDENTLY_VERIFIED"):
        raise ValueError("witness_claim_mismatch")
    if not isinstance(source.get("fixture_sha256"), str) or not HEX64.fullmatch(source["fixture_sha256"]):
        raise ValueError("invalid_fixture_hash")
    return digest


def freeze(args):
    if args.output.exists() or args.output.is_symlink():
        raise ValueError("output_already_exists")
    if not args.integrated_receipt.is_file():
        raise ValueError("integrated_receipt_missing")
    if not args.witness.is_file():
        raise ValueError("witness_file_missing")
    if args.integrated_receipt.is_symlink() or args.witness.is_symlink():
        raise ValueError("evidence_symlink_refused")
    if args.integrated_receipt.stat().st_size > 4_000_000 or args.witness.stat().st_size > 100_000:
        raise ValueError("input_too_large")
    receipt = args.integrated_receipt.read_bytes()
    witness = json.loads(args.witness.read_bytes())
    digest = validate(witness, receipt)
    current = git("rev-parse", "HEAD")
    git("cat-file", "-e", FROZEN_SOURCE_SHA + "^{commit}")
    if not valid_git_commit_sha(current):
        raise ValueError("invalid_head_sha")
    # The frozen commit must be an ancestor of the checked-out source.
    if subprocess.run(["git", "merge-base", "--is-ancestor", FROZEN_SOURCE_SHA, "HEAD"],
                      cwd=ROOT, timeout=12, check=False).returncode:
        raise ValueError("frozen_commit_not_on_checkout")
    status = git("status", "--porcelain", "--untracked-files=no")
    if status:
        raise ValueError("tracked_worktree_not_clean")
    report = {
        "schema": "afya-submission-freeze-1",
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository": "buriro-ezekia/afyaevidence",
        "frozen_source_commit": FROZEN_SOURCE_SHA,
        "auditor_checkout_head": current,
        "historical_ci_green_commit": CI_FIRST_GREEN_SHA,
        "ci_for_frozen_commit": "NOT_VERIFIED",
        "historic_local_regression": {
            "operator_reported": "319_TESTS_PASS",
            "verification_dir": "runtime/identity-verification-20261025T170250936725Z",
            "match_to_frozen_commit": "NOT_ATTESTED_BY_PRIOR_OUTPUT",
        },
        "integrated_receipt_sha256": digest,
        "fixture_receipt_sha256": witness["source_receipts"]["fixture_sha256"],
        "integrated_summary": {
            "modes": ["zetaris", "ollama", "hmem_reference"],
            "explanation_category": "reporting_artefact_supported",
            "recalled_context_count": 0,
            "review_status": "awaiting_human_review",
        },
        "independent_service_attestation": "NOT_VERIFIED",
        "source_records_in_report": "NONE",
        "submission_status": "DRAFT_NOT_SUBMITTED",
        "container_security": "BLOCKED",
        "production_release": "BLOCKED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print("SUBMISSION_FREEZE=PASS")
    print("FROZEN_SOURCE_COMMIT=" + FROZEN_SOURCE_SHA)
    print("AUDITOR_CHECKOUT_HEAD=" + current)
    print("INTEGRATED_RECEIPT_SHA256=" + digest)
    print("CIRCLECI_FROZEN_COMMIT=NOT_VERIFIED")
    print("SOURCE_WORKTREE=CLEAN_TRACKED_FILES")
    print("SUBMISSION_STATUS=DRAFT")
    print("PRODUCTION_RELEASE=BLOCKED")
    print("FREEZE_OUTPUT=" + str(args.output))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--witness", required=True, type=Path)
    ap.add_argument("--integrated-receipt", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    try:
        return freeze(args)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError,
            json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        # No raw Git stderr, receipt data, credentials or arbitrary paths.
        # Only fixed, non-sensitive error codes are permitted on stdout.
        reasons = {
            "output_already_exists", "integrated_receipt_missing",
            "witness_file_missing", "evidence_symlink_refused",
            "input_too_large", "invalid_witness_schema",
            "invalid_witness_body", "integrated_receipt_digest_mismatch",
            "witness_claim_mismatch", "invalid_fixture_hash",
            "git_state_unavailable", "invalid_head_sha",
            "frozen_commit_not_on_checkout", "tracked_worktree_not_clean",
        }
        if isinstance(error, ValueError) and str(error) in reasons:
            reason = str(error)
        elif isinstance(error, json.JSONDecodeError):
            reason = "invalid_witness_json"
        elif isinstance(error, subprocess.TimeoutExpired):
            reason = "git_command_timeout"
        elif isinstance(error, OSError):
            reason = "filesystem_access_error"
        else:
            reason = "unexpected_invalid_evidence"
        print("SUBMISSION_FREEZE=BLOCKED_EVIDENCE_OR_WORKTREE")
        print("SUBMISSION_FREEZE_REASON=" + reason)
        print("SUBMISSION_FREEZE_SOURCE_COMMIT=" + FROZEN_SOURCE_SHA)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
