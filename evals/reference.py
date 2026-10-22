"""Evaluator-only reference: bounded validation, cutoff selection and exact totals.

No model, JDBC or answer-key dependency. This is a fixture oracle, not an agent.
"""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
import hashlib
import json

from afyaevidence.contracts import ALGORITHM, SCHEMAS, canonical_digest, normalise, read_csv

COUNTS = ("suspected_episodes", "tested_episodes", "positive_episodes")


def key(row):
    return (row["dataset_id"], row["report_id"], row["report_version"])


def load_snapshot(directory):
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest["canonical_algorithm"] != ALGORITHM or manifest["schema_version"] != "aggregate-1":
        raise ValueError("Unsupported snapshot contract")
    if set(manifest["tables"]) != set(SCHEMAS):
        raise ValueError("Unexpected source tables")
    tables = {}
    for table, schema in SCHEMAS.items():
        meta = manifest["tables"][table]
        if meta["file"] != f"{table}.csv" or meta["field_order"] != [f for f, _ in schema]:
            raise ValueError("Unexpected source file/schema")
        content = (directory / meta["file"]).read_bytes()
        rows = read_csv(table, content)
        if len(rows) > (6 if table == "facility_registry" else 432):
            raise ValueError("Fixture row cap exceeded")
        if any(r["dataset_id"] != manifest["dataset_id"] for r in rows):
            raise ValueError("Mixed dataset IDs")
        if (len(rows) != meta["row_count"] or
            hashlib.sha256(content).hexdigest() != meta["byte_sha256"] or
            canonical_digest(table, rows) != meta["canonical_sha256"]):
            raise ValueError("Snapshot hash/count mismatch")
        tables[table] = rows
    return manifest, tables


def ratio(numerator, denominator):
    return None if denominator == 0 else float(Fraction(100 * numerator, denominator))


def totals(rows):
    if not rows:
        return dict(tested=None, positive=None, positivity_pct=None,
                    positivity_reason="NO_VALID_REPORTS")
    tested = sum(r["tested_episodes"] for r in rows)
    positive = sum(r["positive_episodes"] for r in rows)
    return dict(tested=tested, positive=positive, positivity_pct=ratio(positive, tested),
                positivity_reason="ZERO_DENOMINATOR" if tested == 0 else None)


def change(before, after):
    if before["positive"] is None or after["positive"] is None:
        positive_delta = positive_pct = None
    else:
        positive_delta = after["positive"] - before["positive"]
        positive_pct = ratio(positive_delta, before["positive"])
    positivity_delta = (None if before["positivity_pct"] is None or after["positivity_pct"] is None
                        else float(Fraction(str(after["positivity_pct"])) -
                                   Fraction(str(before["positivity_pct"]))))
    tested_pct = (None if before["tested"] is None or after["tested"] is None
                  else ratio(after["tested"] - before["tested"], before["tested"]))
    return dict(positive_delta=positive_delta, positive_change_pct=positive_pct,
                tested_change_pct=tested_pct, positivity_change_pp=positivity_delta)


def analyse(tables, *, as_of_utc, comparison_month="2025-10-01", target_month="2025-11-01",
            district_id="D001"):
    normalise(as_of_utc, "timestamp")
    for month in (comparison_month, target_month):
        normalise(month, "month")
    if comparison_month == target_month:
        raise ValueError("Comparison and target must differ")
    registry = tables["facility_registry"]
    if len({(r["dataset_id"], r["facility_id"]) for r in registry}) != len(registry):
        raise ValueError("Conflicting registry key")
    by_facility = {r["facility_id"]: r for r in registry}
    if any(r["active_to"] is not None and r["active_to"] <= r["active_from"] for r in registry):
        raise ValueError("Invalid registry active interval")
    log_groups, report_groups = defaultdict(list), defaultdict(list)
    for event in tables["reporting_log"]:
        if event["received_at_utc"] <= as_of_utc:
            log_groups[key(event)].append(event)
    for report in tables["malaria_monthly"]:
        report_groups[key(report)].append(report)
    findings = set()
    # A log has no period/facility of its own; unresolved joins block this scope.
    integrity_block = False
    for k in log_groups:
        if k not in report_groups:
            findings.add("ORPHAN_LOG")
            integrity_block = True
    for k in report_groups:
        # Reports paired with future events are invisible, rather than missing logs.
        if not any(key(e) == k for e in tables["reporting_log"]):
            findings.add("MISSING_LOG")
            integrity_block = True
    eligible, bad_ids = [], set()
    for k, events in log_groups.items():
        reports = report_groups.get(k, [])
        if not reports:
            continue
        if len(events) != 1 or len(reports) != 1:
            findings.add("CONFLICTING_KEY")
            bad_ids.add(k[1])
            # Retain distinct facility/month identities for receipt coverage only.
            eligible.extend((r, events[0]) for r in reports)
        else:
            eligible.append((reports[0], events[0]))
    by_id = defaultdict(list)
    for report, event in eligible:
        by_id[report["report_id"]].append((report, event))
    for report_id, pairs in by_id.items():
        if len({(r["facility_id"], r["period_month"]) for r, _ in pairs}) != 1:
            findings.add("CONTRADICTORY_REPORT_ID")
            bad_ids.add(report_id)
            integrity_block = True
        if len({r["report_version"] for r, _ in pairs}) > 3:
            raise ValueError("Too many report versions")
    facility_month_ids = defaultdict(set)
    for report, _ in eligible:
        facility_month_ids[(report["facility_id"], report["period_month"])].add(report["report_id"])
        if report["facility_id"] not in by_facility:
            findings.add("UNKNOWN_FACILITY")
            integrity_block = True
    for ids in facility_month_ids.values():
        if len(ids) > 1:
            findings.add("CONFLICTING_FACILITY_MONTH")
            bad_ids.update(ids)
    selected = {}
    for report_id, pairs in by_id.items():
        if report_id not in bad_ids:
            selected[report_id] = max(pairs, key=lambda pair: pair[0]["report_version"])

    def valid(report):
        values = [report[c] for c in COUNTS]
        return (all(value is not None for value in values) and
                0 <= values[2] <= values[1] <= values[0])

    output, usable = {}, {}
    for label, month in (("comparison", comparison_month), ("target", target_month)):
        expected = sorted(r["facility_id"] for r in registry if r["district_id"] == district_id and
                          r["active_from"] <= month and (r["active_to"] is None or month < r["active_to"]))
        received = {r["facility_id"] for r, _ in eligible if r["period_month"] == month and
                    r["facility_id"] in expected}
        accepted, records, excluded, latest = [], [], [], {}
        for report, event in selected.values():
            if report["period_month"] != month or report["facility_id"] not in expected:
                continue
            latest[report["facility_id"]] = report["report_version"]
            reason = None
            if event["status"] == "withdrawn":
                reason = "WITHDRAWN"
            else:
                accepted.append(report["facility_id"])
                if any(report[c] is None for c in COUNTS):
                    reason = "MISSING_COUNT"
                elif not valid(report):
                    reason = "IMPOSSIBLE_COUNTS"
                elif not event["declared_complete"]:
                    reason = "DECLARED_INCOMPLETE"
            if reason:
                findings.add(reason)
                excluded.append(dict(report_id=report["report_id"],
                                     report_version=report["report_version"], reason=reason))
            else:
                records.append(report)
        # Raw diagnostic totals remain bounded by the same observation cutoff.
        raw_rows = [r for r, event in eligible if r["period_month"] == month and
                    r["facility_id"] in expected and r["report_id"] not in bad_ids and
                    event["status"] == "accepted" and valid(r)]
        if len(received) < len(expected):
            findings.add("MISSING_REPORT")
        if integrity_block:
            records = []
        usable[label] = records
        output[label] = dict(
            **totals(records), expected=len(expected), received=len(received),
            accepted=len(accepted), valid=len(records),
            receipt_coverage_pct=ratio(len(received), len(expected)),
            accepted_coverage_pct=ratio(len(accepted), len(expected)),
            analytical_completeness_pct=ratio(len(records), len(expected)),
            availability="unavailable" if not records else "usable" if len(records) == len(expected) else "partial",
            raw=totals([] if integrity_block else raw_rows),
            observed_report_versions=sorted({(r["report_id"], r["report_version"]) for r, _ in eligible
                                             if r["period_month"] == month}),
            latest_versions=dict(sorted(latest.items())), excluded=sorted(excluded, key=lambda r: r["report_id"]),
        )
    common = sorted({r["facility_id"] for r in usable["comparison"]} &
                    {r["facility_id"] for r in usable["target"]})
    matched = {label: totals([r for r in rows if r["facility_id"] in common])
               for label, rows in usable.items()}
    return dict(**output, change=change(output["comparison"], output["target"]),
                matched=dict(facilities=common, **matched,
                             change=change(matched["comparison"], matched["target"])),
                finding_codes=sorted(findings), as_of_utc=as_of_utc)
