"""Contract and metamorphic checks independent of scenario construction arithmetic."""
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from afyaevidence.contracts import canonical_digest, csv_bytes, normalise, read_csv
from evals.evaluate import evaluate
from evals.generate import RECIPES, artifacts, build_tables
from evals.reference import analyse, load_snapshot


class SyntheticTests(unittest.TestCase):
    def tables(self, name="revision"):
        return build_tables(name, RECIPES[name])

    def test_all_independent_scenario_answers(self):
        results = evaluate()
        self.assertEqual(16, len(results))
        self.assertTrue(all(r["status"] == "PASS" for r in results), results)

    def test_generation_is_byte_identical_and_committed(self):
        first, second = artifacts(), artifacts()
        self.assertEqual(first, second)
        self.assertEqual(60, len(first))
        for name, expected in first.items():
            with self.subTest(name=name):
                self.assertEqual(expected, (ROOT / name).read_bytes())

    def test_every_snapshot_has_six_facilities_and_24_month_scope(self):
        for dataset_id in RECIPES.values():
            manifest, tables = load_snapshot(ROOT / "data/synthetic" / dataset_id)
            self.assertEqual(144, manifest["scope"]["expected_facility_months"])
            self.assertEqual(6, len(tables["facility_registry"]))
            self.assertEqual(23 if dataset_id == RECIPES["missing_baseline"] else 24,
                             len({r["period_month"] for r in tables["malaria_monthly"]}))
            self.assertTrue(manifest["synthetic"])
            self.assertNotIn("scenario", manifest)

    def test_core_grain_and_join_are_one_to_one_per_version(self):
        for name in ("expanded_testing", "revision", "unexplained", "mixed"):
            tables = self.tables(name)
            report_keys = [(r["report_id"], r["report_version"]) for r in tables["malaria_monthly"]]
            log_keys = [(r["report_id"], r["report_version"]) for r in tables["reporting_log"]]
            self.assertEqual(len(report_keys), len(set(report_keys)))
            self.assertEqual(set(report_keys), set(log_keys))
            self.assertEqual(len(log_keys), len(set(log_keys)))
            self.assertEqual(144, len({(r["facility_id"], r["period_month"]) for r in tables["malaria_monthly"]}))

    def test_rows_shuffled_preserve_digest_and_analysis(self):
        for name in RECIPES:
            tables = self.tables(name)
            shuffled = deepcopy(tables)
            for table, rows in shuffled.items():
                random.Random(31).shuffle(rows)
                self.assertEqual(canonical_digest(table, tables[table]), canonical_digest(table, rows))
            self.assertEqual(analyse(tables, as_of_utc="2026-01-15T00:00:00Z"),
                             analyse(shuffled, as_of_utc="2026-01-15T00:00:00Z"))

    def test_duplicates_change_content_digest(self):
        rows = self.tables()["facility_registry"]
        self.assertNotEqual(canonical_digest("facility_registry", rows),
                            canonical_digest("facility_registry", rows + rows[:1]))

    def test_byte_and_content_hashes_have_distinct_semantics(self):
        rows = self.tables()["facility_registry"]
        a, b = csv_bytes("facility_registry", rows), csv_bytes("facility_registry", rows[::-1])
        self.assertNotEqual(hashlib.sha256(a).hexdigest(), hashlib.sha256(b).hexdigest())
        self.assertEqual(canonical_digest("facility_registry", read_csv("facility_registry", a)),
                         canonical_digest("facility_registry", read_csv("facility_registry", b)))

    def test_normalisation_preserves_missing_zero_and_bool(self):
        self.assertIsNone(normalise("", "count?"))
        self.assertEqual(0, normalise("0", "count?"))
        self.assertIs(False, normalise("false", "bool"))
        self.assertEqual("2024-01-01", normalise(date(2024, 1, 1), "date"))
        for value in (True, -1, "01", " 1", "1.0", float("inf")):
            with self.assertRaises(ValueError):
                normalise(value, "count?")
        with self.assertRaises(ValueError):
            normalise(datetime(2024, 1, 1), "date")

    def test_invalid_date_status_schema_are_rejected(self):
        for value, kind in (("2024-02-30", "date"), ("2024-02-02", "month"),
                            ("2024-01-01T12:00:00+00:00", "timestamp"),
                            ("2024-01-01T12:00:00.1Z", "timestamp"),
                            ("pending", "status"), ("FALSE", "bool")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalise(value, kind)
        with self.assertRaises(ValueError):
            read_csv("facility_registry", b"dataset_id,facility_id\na,F001\n")

    def test_future_version_not_exposed_before_cutoff(self):
        tables = self.tables("delayed_revision")
        before = analyse(tables, as_of_utc="2025-12-10T00:00:00Z")
        reduced = deepcopy(tables)
        for name in ("malaria_monthly", "reporting_log"):
            reduced[name] = [r for r in reduced[name] if r["report_version"] == 1]
        self.assertEqual(before, analyse(reduced, as_of_utc="2025-12-10T00:00:00Z"))
        self.assertNotIn(("R202511001", 2), before["target"]["observed_report_versions"])

    def test_cutoff_is_inclusive(self):
        tables = self.tables("delayed_revision")
        at = analyse(tables, as_of_utc="2025-12-20T12:00:00Z")
        before = analyse(tables, as_of_utc="2025-12-20T11:59:59Z")
        self.assertEqual(2, at["target"]["latest_versions"]["F001"])
        self.assertEqual(1, before["target"]["latest_versions"]["F001"])

    def test_higher_version_wins_over_later_arrival_of_old_version(self):
        tables = self.tables("delayed_revision")
        next(r for r in tables["reporting_log"] if r["report_id"] == "R202511001" and
             r["report_version"] == 1)["received_at_utc"] = "2025-12-22T12:00:00Z"
        actual = analyse(tables, as_of_utc="2026-01-15T00:00:00Z")
        self.assertEqual(2, actual["target"]["latest_versions"]["F001"])
        self.assertEqual(115, actual["target"]["positive"])

    def test_invalid_withdrawn_latest_do_not_fall_back(self):
        for name, code in (("latest_invalid", "IMPOSSIBLE_COUNTS"), ("latest_withdrawn", "WITHDRAWN")):
            actual = analyse(self.tables(name), as_of_utc="2026-01-15T00:00:00Z")
            self.assertEqual(80, actual["target"]["positive"])
            self.assertEqual([dict(report_id="R202511001", report_version=2, reason=code)],
                             actual["target"]["excluded"])
            self.assertEqual(6, actual["target"]["received"])

    def test_true_zero_baseline_has_undefined_percentage_change(self):
        tables = self.tables("zero_denominator")
        for row in tables["malaria_monthly"]:
            if row["period_month"] == "2025-10-01":
                row["positive_episodes"] = 0
        actual = analyse(tables, as_of_utc="2026-01-15T00:00:00Z")
        self.assertEqual(0, actual["change"]["positive_delta"])
        self.assertIsNone(actual["change"]["positive_change_pct"])

    def test_positivity_is_weighted_not_mean_of_facility_rates(self):
        tables = self.tables("unexplained")
        positives = [r for r in tables["malaria_monthly"] if r["period_month"] == "2025-11-01"]
        actual = analyse(tables, as_of_utc="2026-01-15T00:00:00Z")
        self.assertEqual(35, actual["target"]["positivity_pct"])
        # Perturb a small facility to expose an otherwise coincidental equal average.
        positives[-1]["positive_episodes"] = 10
        weighted = analyse(tables, as_of_utc="2026-01-15T00:00:00Z")["target"]["positivity_pct"]
        unweighted = sum(100*r["positive_episodes"]/r["tested_episodes"] for r in positives)/6
        self.assertNotEqual(unweighted, weighted)
        self.assertEqual(33.6, weighted)

    def test_missing_logs_and_multiple_report_ids_cannot_vanish(self):
        tables = self.tables()
        tables["reporting_log"] = [r for r in tables["reporting_log"] if r["report_id"] != "R202511002"]
        actual = analyse(tables, as_of_utc="2026-01-15T00:00:00Z")
        self.assertIn("MISSING_LOG", actual["finding_codes"])
        self.assertEqual("unavailable", actual["target"]["availability"])
        tables = self.tables()
        for table in ("malaria_monthly", "reporting_log"):
            row = deepcopy(next(r for r in tables[table] if r["report_id"] == "R202511002"))
            row["report_id"] = "R202511902"
            tables[table].append(row)
        actual = analyse(tables, as_of_utc="2026-01-15T00:00:00Z")
        self.assertIn("CONFLICTING_FACILITY_MONTH", actual["finding_codes"])
        self.assertEqual(5, actual["target"]["valid"])

    def test_snapshot_tampering_fails_before_analysis(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source = ROOT / "data/synthetic" / RECIPES["revision"]
            for file in source.iterdir():
                (directory / file.name).write_bytes(file.read_bytes())
            path = directory / "malaria_monthly.csv"
            path.write_bytes(path.read_bytes().replace(b",100,20\n", b",100,21\n", 1))
            with self.assertRaisesRegex(ValueError, "hash/count mismatch"):
                load_snapshot(directory)

    def test_manifest_paths_and_row_caps_are_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source = ROOT / "data/synthetic" / RECIPES["revision"]
            for file in source.iterdir():
                (directory / file.name).write_bytes(file.read_bytes())
            manifest = json.loads((directory / "manifest.json").read_text())
            manifest["tables"]["facility_registry"]["file"] = "../../secret.csv"
            (directory / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "Unexpected source"):
                load_snapshot(directory)

    def test_check_cli_is_read_only(self):
        before = {name: (ROOT/name).read_bytes() for name in artifacts()}
        result = subprocess.run([sys.executable, "scripts/generate_synthetic.py", "--check"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("SYNTHETIC_REPRODUCIBILITY=PASS", result.stdout)
        self.assertEqual(before, {name: (ROOT/name).read_bytes() for name in before})

    def test_runtime_package_has_no_evaluator_import(self):
        for path in (ROOT / "src").rglob("*.py"):
            self.assertNotIn("from evals", path.read_text())
            self.assertNotIn("import evals", path.read_text())

    def test_staging_copies_only_sources_and_refuses_overwrite(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("stage_synthetic", ROOT / "scripts/stage_synthetic.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "upload"
            module.stage(RECIPES["revision"], destination)
            self.assertEqual({"facility_registry.csv", "malaria_monthly.csv", "reporting_log.csv", "manifest.json"},
                             {p.name for p in destination.iterdir()})
            with self.assertRaises(ValueError):
                module.stage(RECIPES["revision"], destination)
            with self.assertRaises(ValueError):
                module.stage("../../evals", Path(temp) / "other")

    def test_wheel_guard_rejects_accidental_answer_key(self):
        import importlib.util
        import zipfile
        spec = importlib.util.spec_from_file_location("check_runtime_package", ROOT / "scripts/check_runtime_package.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.whl"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("afyaevidence/__init__.py", "")
                archive.writestr("afyaevidence/contracts.py", "")
                archive.writestr("evals/scenario_answers.json", "{}")
            with self.assertRaisesRegex(ValueError, "Unexpected runtime member"):
                module.check(path)


if __name__ == "__main__":
    unittest.main()
