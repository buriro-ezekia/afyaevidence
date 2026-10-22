"""Deterministic two-month reporting calculations; no model or evaluator imports."""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
import json

from .contracts import normalise
from .snapshot import digest

COUNTS = ("suspected_episodes", "tested_episodes", "positive_episodes")
CALCULATION_VERSION = "reporting-1"


def key(row):
    return (row["dataset_id"], row["report_id"], row["report_version"])


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


def _calculate(tables, *, as_of_utc, comparison_month="2025-10-01", target_month="2025-11-01",
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
    all_reports = defaultdict(list)
    months = {comparison_month, target_month}
    for report in tables["malaria_monthly"]:
        all_reports[key(report)].append(report)
        if report["period_month"] in months:
            report_groups[key(report)].append(report)
    for event in tables["reporting_log"]:
        if event["received_at_utc"] <= as_of_utc and (
            key(event) in report_groups or key(event) not in all_reports
        ):
            log_groups[key(event)].append(event)
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


@dataclass(frozen=True)
class Request:
    district_id: str = "D001"
    comparison_month: str = "2025-10-01"
    target_month: str = "2025-11-01"
    as_of_utc: str = "2026-01-15T00:00:00Z"

    def __post_init__(self):
        if self.district_id != "D001":
            raise ValueError("District is outside the registered synthetic scope")
        for month in (self.comparison_month, self.target_month):
            normalise(month, "month")
            if not "2024-01-01" <= month <= "2025-12-01":
                raise ValueError("Month is outside the registered synthetic scope")
        if self.comparison_month >= self.target_month:
            raise ValueError("Comparison month must precede target month")
        normalise(self.as_of_utc, "timestamp")


@dataclass(frozen=True)
class Bundle:
    """Canonical JSON is immutable; every access returns detached values."""
    _json: str

    def to_dict(self):
        return json.loads(self._json)

    def resolve_evidence(self, ids):
        if len(ids) > 20 or len(set(ids)) != len(ids):
            raise ValueError("Request at most 20 distinct evidence IDs")
        registry = {r["evidence_id"]: r for r in self.to_dict()["evidence_records"]}
        if any(eid not in registry for eid in ids):
            raise ValueError("Evidence ID is outside this investigation")
        return [registry[eid] for eid in ids]

    def resolve_metrics(self, ids):
        registry = {r["metric_ref"]: r for r in self.to_dict()["metrics"]}
        if len(ids) > 50 or len(set(ids)) != len(ids) or any(mid not in registry for mid in ids):
            raise ValueError("Invalid or out-of-scope metric references")
        return [registry[mid] for mid in ids]


def decimal_value(value):
    if value is None:
        return None
    if value.denominator == 1:
        return value.numerator
    with localcontext() as context:
        context.prec = 28
        return format(Decimal(value.numerator) / Decimal(value.denominator), ".12f").rstrip("0").rstrip(".")


def investigate(snapshot, request=None):
    request = request or Request()
    tables = snapshot.tables()
    scope = dict(district_id=request.district_id, comparison_month=request.comparison_month,
                 target_month=request.target_month, as_of_utc=request.as_of_utc)
    summary = _calculate(tables, **scope)
    analysis_id = "an_" + digest([CALCULATION_VERSION, snapshot.snapshot_id, scope])
    months = {request.comparison_month, request.target_month}
    reports = tables["malaria_monthly"]
    logs = tables["reporting_log"]
    events_by_key = defaultdict(list)
    all_log_keys = {key(event) for event in logs}
    for event in logs:
        if event["received_at_utc"] <= request.as_of_utc:
            events_by_key[key(event)].append(event)
    report_index = defaultdict(list)
    for report in reports:
        report_index[key(report)].append(report)
    visible = {
        "facility_registry": [r for r in tables["facility_registry"] if r["district_id"] == request.district_id],
        "malaria_monthly": [r for r in reports if r["period_month"] in months and
                            (key(r) in events_by_key or key(r) not in all_log_keys)],
        "reporting_log": [e for e in logs if e["received_at_utc"] <= request.as_of_utc and
                          (key(e) not in report_index or
                           any(r["period_month"] in months for r in report_index[key(e)]))],
    }
    evidence = []
    for table, rows in visible.items():
        occurrences = defaultdict(int)
        for row in rows:
            content_hash = digest([table, row])
            occurrence = occurrences[content_hash]
            occurrences[content_hash] += 1
            eid = "ev_" + digest([analysis_id, table, content_hash, occurrence])
            evidence.append(dict(evidence_id=eid, snapshot_id=snapshot.snapshot_id,
                                 analysis_id=analysis_id, table=table, record=row,
                                 content_sha256=content_hash, occurrence=occurrence,
                                 source_table_sha256=dict(snapshot.source_hashes)[table]))
    evidence.sort(key=lambda item: item["evidence_id"])
    registry_ids = [e["evidence_id"] for e in evidence if e["table"] == "facility_registry"]
    period_evidence = {}
    for label, month in (("comparison", request.comparison_month), ("target", request.target_month)):
        record_keys = {key(r) for r in visible["malaria_monthly"] if r["period_month"] == month}
        period_evidence[label] = sorted(registry_ids + [e["evidence_id"] for e in evidence
            if e["table"] != "facility_registry" and key(e["record"]) in record_keys])
    all_ids = sorted(e["evidence_id"] for e in evidence)
    metrics = []

    def fact(name, value, unit, period, cohort, view, ids, availability, reason=None):
        availability = "available" if availability == "usable" else availability
        exact = None if value is None else Fraction(value)
        identity = [analysis_id, name, period, cohort, view]
        if period in {"comparison", "target"}:
            source = summary["matched"][period] if cohort == "matched" else summary[period]
            if view == "raw_diagnostic":
                source = source["raw"]
            inputs = {k: source[k] for k in ("tested", "positive", "expected", "received", "accepted", "valid") if k in source}
        else:
            source = summary["matched"] if cohort == "matched" else summary
            inputs = {p: {k: source[p][k] for k in ("tested", "positive")} for p in ("comparison", "target")}
        metrics.append(dict(metric_ref="mf_" + digest(identity), name=name,
            value=decimal_value(exact), numerator=None if exact is None else exact.numerator,
            denominator=None if exact is None else exact.denominator, unit=unit,
            period=period, cohort=cohort, view=view, evidence_ids=sorted(ids),
            availability="unavailable" if exact is None else availability,
            reason=reason or ("INCOMPLETE_COVERAGE" if availability == "partial" else None),
            input_values=inputs, exact_value_format="rational numerator/denominator; decimal value rounded to 12 places",
            calculation_version=CALCULATION_VERSION,
            analysis_id=analysis_id, snapshot_id=snapshot.snapshot_id))

    def add_totals(values, label, cohort, view, ids, state):
        for field in ("tested", "positive"):
            fact(field + "_total", values[field], "episodes", label, cohort, view, ids, state,
                 "NO_VALID_REPORTS" if values[field] is None else None)
        tested, positive = values["tested"], values["positive"]
        positivity = None if tested in (None, 0) else Fraction(100 * positive, tested)
        fact("positivity_pct", positivity, "percent", label, cohort, view, ids, state,
             "NO_VALID_REPORTS" if tested is None else "ZERO_DENOMINATOR" if tested == 0 else None)

    def add_changes(before, after, cohort, ids, state):
        for field in ("tested", "positive"):
            a, b = before[field], after[field]
            delta = None if a is None or b is None else b - a
            fact(field + "_delta", delta, "episodes", "comparison_to_target", cohort, "canonical", ids, state,
                 "INSUFFICIENT_COMPARATIVE_DATA" if delta is None else None)
            pct = None if delta is None or a == 0 else Fraction(100 * delta, a)
            fact(field + "_change_pct", pct, "percent", "comparison_to_target", cohort, "canonical", ids, state,
                 "INSUFFICIENT_COMPARATIVE_DATA" if delta is None else "ZERO_BASELINE" if a == 0 else None)
        a, b = before["tested"], after["tested"]
        pp = None if a in (None, 0) or b in (None, 0) else (
            Fraction(100 * after["positive"], b) - Fraction(100 * before["positive"], a))
        fact("positivity_change_pp", pp, "percentage_points", "comparison_to_target", cohort,
             "canonical", ids, state, "POSITIVITY_UNAVAILABLE" if pp is None else None)

    for label in ("comparison", "target"):
        period = summary[label]
        ids = period_evidence[label]
        for view, values in (("canonical", period), ("raw_diagnostic", period["raw"])):
            add_totals(values, label, "all_available", view, ids, period["availability"])
        for field in ("expected", "received", "accepted", "valid"):
            fact(field + "_facilities", period[field], "facilities", label, "expected", "quality",
                 ids, "available")
        for field in ("received", "accepted", "valid"):
            val = None if period["expected"] == 0 else Fraction(100*period[field], period["expected"])
            fact(field + "_coverage_pct", val, "percent", label, "expected", "quality", ids, "available",
                 "ZERO_EXPECTED" if val is None else None)
        add_totals(summary["matched"][label], label, "matched", "canonical", ids,
                   "available" if summary["matched"]["facilities"] else "unavailable")
    comparison_state = "available" if all(summary[p]["availability"] == "usable" for p in ("comparison", "target")) else "partial"
    add_changes(summary["comparison"], summary["target"], "all_available", all_ids, comparison_state)
    add_changes(summary["matched"]["comparison"], summary["matched"]["target"], "matched", all_ids,
                "available" if summary["matched"]["facilities"] else "unavailable")
    # Findings are observations, not diagnoses or causal conclusions. Full bounded
    # scope evidence includes denominator and excluded records, not just winners.
    findings = [dict(code=code, evidence_ids=all_ids) for code in summary["finding_codes"]]
    quality = {}
    contributions = []
    for label, month in (("comparison", request.comparison_month), ("target", request.target_month)):
        expected_facilities = sorted(r["facility_id"] for r in visible["facility_registry"] if
            r["active_from"] <= month and (r["active_to"] is None or month < r["active_to"]))
        received_facilities = sorted({r["facility_id"] for r in visible["malaria_monthly"] if
            r["period_month"] == month and key(r) in events_by_key and r["facility_id"] in expected_facilities})
        revisions = []
        for facility in expected_facilities:
            observed = [r for r in visible["malaria_monthly"] if r["facility_id"] == facility and
                        r["period_month"] == month and key(r) in events_by_key]
            versions = sorted({r["report_version"] for r in observed})
            if len(versions) > 1:
                revisions.append(dict(facility_id=facility, observed_versions=versions,
                                      latest_observed_version=max(versions), evidence_ids=period_evidence[label]))
        quality[label] = dict(expected_facilities=expected_facilities, received_facilities=received_facilities,
            missing_facilities=sorted(set(expected_facilities)-set(received_facilities)),
            unmatched_facilities=sorted(set(expected_facilities)-set(summary["matched"]["facilities"])),
            revisions=revisions, exclusions=summary[label]["excluded"])
    for facility in summary["matched"]["facilities"]:
        values = {}
        for label, month in (("comparison", request.comparison_month), ("target", request.target_month)):
            version = summary[label]["latest_versions"][facility]
            record = next(r for r in visible["malaria_monthly"] if r["facility_id"] == facility and
                          r["period_month"] == month and r["report_version"] == version)
            values[label] = dict(tested=record["tested_episodes"], positive=record["positive_episodes"])
        contributions.append(dict(facility_id=facility, **values,
            positive_delta=values["target"]["positive"]-values["comparison"]["positive"],
            tested_delta=values["target"]["tested"]-values["comparison"]["tested"], evidence_ids=all_ids))
    result = dict(schema_version="analysis-1", calculation_version=CALCULATION_VERSION,
        analysis_id=analysis_id, snapshot_id=snapshot.snapshot_id, dataset_id=snapshot.dataset_id,
        data_mode=snapshot.data_mode, model_mode="not_run", memory_mode="not_run",
        manifest_sha256=snapshot.manifest_sha256, source_hashes=dict(snapshot.source_hashes),
        retrieved_at_utc=snapshot.retrieved_at_utc, source_namespace=snapshot.source_namespace,
        query_template_version="jdbc-bounded-1" if snapshot.data_mode == "zetaris" else "fixture-byte-1",
        scope=scope, summary=summary, summary_values="display_only; exact values are in metric facts",
        quality=quality, matched_facility_contributions=contributions,
        evidence_records=evidence, metrics=sorted(metrics, key=lambda m:m["metric_ref"]), findings=findings,
        limitations=["Synthetic aggregate data; no causal or outbreak conclusion", 
                     "Raw diagnostic totals must not be treated as latest-version counts",
                     "All-available comparisons may have different facility coverage; inspect matched totals",
                     "Evidence lists include scope records and excluded versions for reproducibility"],
        status="complete" if comparison_state == "available" else "partial" if summary["matched"]["facilities"] else "insufficient_data")
    return Bundle(json.dumps(result, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
