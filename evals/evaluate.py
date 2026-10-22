"""Fixture acceptance harness. This does not run a model or sponsor service."""
import argparse
import json
import re
from pathlib import Path

from evals.reference import analyse, load_snapshot

ROOT = Path(__file__).resolve().parents[1]


def compare(expected, actual, path=""):
    errors = []
    for name, value in expected.items():
        location = f"{path}.{name}".lstrip(".")
        if name not in actual:
            errors.append(f"{location}: missing")
        elif isinstance(value, dict):
            errors.extend(compare(value, actual[name], location))
        elif value != actual[name]:
            errors.append(f"{location}: expected {value!r}; got {actual[name]!r}")
    return errors


def evaluate(root=ROOT):
    key = json.loads((root / "evals/scenario_answers.json").read_text(encoding="utf-8"))
    results = []
    for case in key["cases"]:
        try:
            dataset_id = case["dataset_id"]
            # Evaluator-controlled identifiers still cannot become arbitrary paths.
            if not re.fullmatch(r"fx_[0-9a-f]{8}", dataset_id):
                raise ValueError("Invalid fixture ID")
            _, tables = load_snapshot(root / "data/synthetic" / dataset_id)
            actual = analyse(tables, as_of_utc=case["as_of_utc"])
            errors = compare(case["expected"], actual)
            observed = {tuple(v) for v in actual["target"]["observed_report_versions"]}
            for version in case.get("required_report_versions", []):
                if tuple(version) not in observed:
                    errors.append(f"Required report version absent: {version}")
            for version in case.get("forbidden_report_versions", []):
                if tuple(version) in observed:
                    errors.append(f"Future report version exposed: {version}")
        except (ValueError, KeyError, OSError) as exc:
            errors = [f"Snapshot evaluation failed: {exc}"]
        results.append(dict(case_id=case["case_id"], mode="fixture",
                            status="FAIL" if errors else "PASS", errors=errors))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print a machine-readable receipt")
    args = parser.parse_args(argv)
    results = evaluate()
    success = all(r["status"] == "PASS" for r in results) and bool(results)
    if args.json:
        print(json.dumps(dict(mode="fixture", status="PASS" if success else "FAIL", cases=results,
                              live_zetaris="NOT_RUN", live_model="NOT_RUN", live_hmem="NOT_RUN"), indent=2))
    else:
        for result in results:
            print(f'{result["case_id"]}={result["status"]}')
            for error in result["errors"]:
                print(f"  {error}")
        print(f'SYNTHETIC_EVALUATION={"PASS" if success else "FAIL"}\nEVALUATION_CASES={len(results)}')
        print("LIVE_ZETARIS=NOT_RUN\nLIVE_MODEL=NOT_RUN\nLIVE_HMEM=NOT_RUN")
    return 0 if success else 1
