"""Runtime tests compare independent expectations and challenge provenance boundaries."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from dataclasses import FrozenInstanceError
import io
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from afyaevidence.analysis import Request, investigate
from afyaevidence.cli import main
from afyaevidence.jdbc import JdbcGateway, DRIVER_FILENAME
from afyaevidence.snapshot import FixtureGateway, SourceError, freeze, read_manifest
from evals.evaluate import compare
from test_verify_zetaris_snapshot import Cursor, Connection


class RuntimeTests(unittest.TestCase):
    def snapshot(self, dataset="fx_32e8b610"):
        return FixtureGateway().collect(ROOT / "data/synthetic" / dataset)

    def test_runtime_matches_all_independent_answers(self):
        answers = json.loads((ROOT / "evals/scenario_answers.json").read_text())
        for case in answers["cases"]:
            with self.subTest(case=case["case_id"]):
                result = investigate(self.snapshot(case["dataset_id"]), Request(as_of_utc=case["as_of_utc"])).to_dict()
                # JSON changes tuples to arrays; the declared answer fields have neither.
                self.assertEqual([], compare(case["expected"], result["summary"]))
                self.assertEqual("fixture", result["data_mode"])
                self.assertEqual("not_run", result["model_mode"])

    def test_snapshot_and_bundle_are_immutable_and_detached(self):
        snapshot = self.snapshot()
        with self.assertRaises(FrozenInstanceError):
            snapshot.dataset_id = "changed"
        tables = snapshot.tables()
        tables["malaria_monthly"][0]["positive_episodes"] = 999
        self.assertNotEqual(999, snapshot.rows("malaria_monthly")[0]["positive_episodes"])
        bundle = investigate(snapshot)
        exported = bundle.to_dict()
        exported["summary"]["target"]["positive"] = 999
        self.assertEqual(100, bundle.to_dict()["summary"]["target"]["positive"])

    def test_row_order_does_not_change_snapshot_or_bundle(self):
        path = ROOT / "data/synthetic/fx_32e8b610"
        snapshot = self.snapshot()
        manifest, sha = read_manifest(path)
        tables = snapshot.tables()
        for rows in tables.values():
            random.Random(45).shuffle(rows)
        shuffled = freeze(manifest, sha, tables, "fixture")
        self.assertEqual(snapshot, shuffled)
        self.assertEqual(investigate(snapshot).to_dict(), investigate(shuffled).to_dict())

    def test_evidence_and_metric_ids_are_scope_bound_and_resolvable(self):
        bundle = investigate(self.snapshot())
        result = bundle.to_dict()
        ids = {e["evidence_id"] for e in result["evidence_records"]}
        self.assertEqual(len(ids), len(result["evidence_records"]))
        for fact in result["metrics"]:
            self.assertTrue(set(fact["evidence_ids"]) <= ids)
            self.assertEqual([fact], bundle.resolve_metrics([fact["metric_ref"]]))
        self.assertEqual(1, len(bundle.resolve_evidence([next(iter(ids))])))
        other = investigate(self.snapshot(), Request(as_of_utc="2025-12-06T00:00:00Z"))
        with self.assertRaises(ValueError):
            other.resolve_evidence([next(iter(ids))])
        with self.assertRaises(ValueError):
            bundle.resolve_metrics(["mf_fabricated"])
        with self.assertRaises(ValueError):
            bundle.resolve_evidence(list(ids)[:21])

    def test_no_future_version_in_visible_evidence_or_revision_lists(self):
        result = investigate(self.snapshot(), Request(as_of_utc="2025-12-06T00:00:00Z")).to_dict()
        for e in result["evidence_records"]:
            self.assertNotEqual(("R202511001", 2), (e["record"].get("report_id"), e["record"].get("report_version")))
        self.assertEqual([], result["quality"]["target"]["revisions"])
        self.assertEqual(500, result["summary"]["target"]["raw"]["tested"])

    def test_metric_exactness_and_undefined_reasons(self):
        result = investigate(self.snapshot("fx_58f1a946")).to_dict()
        metric = next(m for m in result["metrics"] if m["name"] == "positivity_pct" and
                      m["period"] == "target" and m["view"] == "raw_diagnostic")
        self.assertEqual((145, 6), (metric["numerator"], metric["denominator"]))
        self.assertEqual({"tested":600,"positive":145},metric["input_values"])
        self.assertEqual("24.166666666667", metric["value"])
        result = investigate(self.snapshot("fx_7c3e912f")).to_dict()
        for metric in result["metrics"]:
            if metric["name"] == "positivity_pct" and metric["period"] == "target":
                self.assertIsNone(metric["value"])
                self.assertEqual("ZERO_DENOMINATOR", metric["reason"])

    def test_partial_coverage_and_contributions_are_explicit(self):
        result = investigate(self.snapshot("fx_d394f785")).to_dict()
        self.assertEqual(["F001"], result["quality"]["target"]["missing_facilities"])
        self.assertEqual("partial", result["status"])
        self.assertEqual(5, len(result["matched_facility_contributions"]))
        self.assertTrue(all(r["positive_delta"] == 0 for r in result["matched_facility_contributions"]))

    def test_request_validation(self):
        for kwargs in (dict(district_id="D002"), dict(target_month="2026-01-01"),
                       dict(target_month="2025-11-02"), dict(as_of_utc="today"),
                       dict(comparison_month="2025-11-01")):
            with self.assertRaises(ValueError):
                Request(**kwargs)

    def gateway(self, temp, cursor):
        jar = Path(temp) / DRIVER_FILENAME
        jar.touch()
        connection = Connection(cursor)
        gateway = JdbcGateway(jar=jar, password="hidden", database="AFYAEVIDENCE_REVISION",
                              connect=lambda *args: connection)
        return gateway, connection

    def test_jdbc_matches_fixture_snapshot_and_runtime_results(self):
        fixture = self.snapshot()
        with tempfile.TemporaryDirectory() as temp:
            cursor = Cursor(fixture.tables(), [])
            gateway, connection = self.gateway(temp, cursor)
            live = gateway.collect(ROOT / "data/synthetic/fx_32e8b610")
            self.assertEqual(fixture.snapshot_id, live.snapshot_id)
            self.assertEqual("zetaris", live.data_mode)
            self.assertEqual("admin@zetaris.com", gateway.username)
            self.assertEqual(investigate(fixture).to_dict()["summary"], investigate(live).to_dict()["summary"])
            self.assertEqual(4, len(cursor.calls))
            self.assertTrue(all(s.startswith("SELECT ") and ";" not in s for s in cursor.calls))
            self.assertTrue(cursor.closed and connection.closed)

    def test_jdbc_failure_and_hash_mismatch_never_fall_back(self):
        for kind in ("driver", "changed", "overflow"):
            with tempfile.TemporaryDirectory() as temp:
                cursor = Cursor(self.snapshot().tables(), [])
                if kind == "driver":
                    cursor.failure = "malaria_monthly"
                elif kind == "changed":
                    cursor.tables["malaria_monthly"][0]["positive_episodes"] += 1
                else:
                    cursor.tables["facility_registry"] *= 400
                gateway, connection = self.gateway(temp, cursor)
                with patch.object(FixtureGateway, "collect", side_effect=AssertionError("No fallback")):
                    with self.assertRaises(SourceError) as error:
                        gateway.collect(ROOT / "data/synthetic/fx_32e8b610")
                self.assertNotIn("secret-password", str(error.exception))
                self.assertTrue(cursor.closed and connection.closed)

    def test_jdbc_rejects_wrong_driver_and_identifiers(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / DRIVER_FILENAME
            path.touch()
            for database, jar in (("A;DROP", path), ("A.B", path), ("A", Path(temp)/"hive.jar")):
                with self.assertRaises(SourceError):
                    JdbcGateway(jar=jar, password="hidden", database=database)

    def test_cli_receipt_and_no_overwrite_or_false_live_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            receipt = Path(temp) / "receipt.json"
            argv = ["--mode", "fixture", "--snapshot", str(ROOT / "data/synthetic/fx_32e8b610"), "--output", str(receipt)]
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main(argv))
            self.assertIn("LIVE_ZETARIS=NOT_RUN", output.getvalue())
            before = receipt.read_bytes()
            self.assertEqual("fixture", json.loads(before)["data_mode"])
            with redirect_stderr(output):
                self.assertEqual(1, main(argv))
            self.assertEqual(before, receipt.read_bytes())

    def test_no_runtime_import_of_evaluator_scripts_or_answers(self):
        import ast
        for path in (ROOT / "src/afyaevidence").glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or "").startswith(("evals", "scripts")))
                if isinstance(node, ast.Import):
                    self.assertTrue(all(not alias.name.startswith(("evals", "scripts")) for alias in node.names))
            self.assertNotIn("scenario_answers", path.read_text())

    def test_full_snapshot_archive_is_detached_and_refuses_overwrite(self):
        snapshot = self.snapshot()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "private-snapshot.json"
            snapshot.write(path)
            before = path.read_bytes()
            saved = json.loads(before)
            self.assertEqual(145, len(saved["tables"]["malaria_monthly"]))
            self.assertEqual(snapshot.snapshot_id, saved["snapshot_id"])
            with self.assertRaises(FileExistsError):
                snapshot.write(path)
            self.assertEqual(before, path.read_bytes())

    def test_unrelated_known_period_does_not_poison_selected_scope(self):
        snapshot = self.snapshot()
        manifest, sha = read_manifest(ROOT / "data/synthetic/fx_32e8b610")
        tables = snapshot.tables()
        row = next(r for r in tables["malaria_monthly"] if r["period_month"] == "2024-01-01")
        row["facility_id"] = "F999"
        from afyaevidence.contracts import canonical_digest
        manifest["tables"]["malaria_monthly"]["canonical_sha256"] = canonical_digest("malaria_monthly", tables["malaria_monthly"])
        changed = freeze(manifest, sha, tables, "fixture")
        result = investigate(changed).to_dict()
        self.assertEqual([], result["summary"]["finding_codes"])
        self.assertEqual(100, result["summary"]["target"]["positive"])


if __name__ == "__main__":
    unittest.main()
