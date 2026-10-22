"""JDBC snapshot checks use fake transports; no fake result is labelled live here."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from scripts import verify_zetaris_snapshot as verifier
from evals.reference import load_snapshot


class Cursor:
    def __init__(self, tables, joined, failure=None):
        self.tables = tables
        self.joined = joined
        self.failure = failure
        self.calls = []
        self.rows = []
        self.closed = False

    def execute(self, statement):
        self.calls.append(statement)
        if self.failure and self.failure in statement:
            raise RuntimeError("secret-password-and-driver-url")
        if statement == "SELECT 1":
            self.rows = [(1,)]
        elif " JOIN " in statement:
            self.rows = list(self.joined)
        else:
            table = statement.split(" FROM ")[1].split(" LIMIT ")[0].split(".")[1]
            fields = [f for f, _ in verifier.SCHEMAS[table]]
            self.rows = [tuple(r[f] for f in fields) for r in self.tables[table]]

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchmany(self, size):
        rows, self.rows = self.rows[:size], self.rows[size:]
        return rows

    def close(self):
        self.closed = True


class Connection:
    def __init__(self, cursor):
        self.handle = cursor
        self.closed = False

    def cursor(self):
        return self.handle

    def close(self):
        self.closed = True


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.manifest, self.fixture = load_snapshot(ROOT / "data/synthetic/fx_32e8b610")
        self.cursor = Cursor(deepcopy(self.fixture), verifier.joined_reference(self.fixture))
        self.connection = Connection(self.cursor)
        self.output = io.StringIO()
        self.connect_args = None

    def connect(self, *args):
        self.connect_args = args
        return self.connection

    def run_check(self, cutoff=verifier.DEFAULT_CUTOFF):
        with redirect_stdout(self.output):
            verifier.check_live(self.connect, jar=Path('/tmp') / 'driver.jar',
                url=verifier.DEFAULT_URL, username="test", password="hidden",
                database=verifier.DEFAULT_DATABASE, dataset_id=verifier.DEFAULT_DATASET,
                manifest=self.manifest, fixture=self.fixture, as_of_utc=cutoff)

    def test_complete_snapshot_hashes_join_and_totals(self):
        self.run_check()
        output = self.output.getvalue()
        self.assertIn("ZETARIS_SNAPSHOT=PASS", output)
        self.assertIn("ZETARIS_JOIN_ROWS=145", output)
        self.assertIn("TARGET_RAW_TESTED=600", output)
        self.assertIn("TARGET_RAW_POSITIVE=120", output)
        self.assertIn("TARGET_CANONICAL_TESTED=500", output)
        self.assertIn("TARGET_CANONICAL_POSITIVE=100", output)
        self.assertEqual(verifier.DRIVER_CLASS, self.connect_args[0])
        self.assertEqual(["test", "hidden"], self.connect_args[2])
        self.assertEqual(5, len(self.cursor.calls))
        self.assertTrue(all(s.startswith("SELECT ") and ";" not in s for s in self.cursor.calls))
        self.assertTrue(self.cursor.closed and self.connection.closed)

    def test_row_order_does_not_change_reconciliation(self):
        for rows in self.cursor.tables.values():
            rows.reverse()
        self.cursor.joined.reverse()
        self.run_check()
        self.assertIn("ZETARIS_SNAPSHOT=PASS", self.output.getvalue())

    def test_changed_value_rejected_and_no_final_pass(self):
        self.cursor.tables["malaria_monthly"][0]["positive_episodes"] += 1
        with self.assertRaisesRegex(verifier.VerificationFailure, "hash differs"):
            self.run_check()
        self.assertNotIn("ZETARIS_SNAPSHOT=PASS", self.output.getvalue())
        self.assertTrue(self.cursor.closed and self.connection.closed)

    def test_same_count_duplicate_missing_and_wrong_dataset_rejected(self):
        for mutation in ("duplicate", "dataset"):
            self.setUp()
            rows = self.cursor.tables["malaria_monthly"]
            if mutation == "duplicate":
                rows[0] = deepcopy(rows[1])
            else:
                rows[0]["dataset_id"] = "fx_00000000"
            with self.assertRaises(verifier.VerificationFailure):
                self.run_check()

    def test_extra_or_missing_rows_fail(self):
        for extra in (True, False):
            self.setUp()
            rows = self.cursor.tables["reporting_log"]
            if extra:
                rows.append(deepcopy(rows[0]))
            else:
                rows.pop()
            with self.assertRaisesRegex(verifier.VerificationFailure, "row count"):
                self.run_check()

    def test_damaged_join_with_same_row_count_fails(self):
        self.cursor.joined[0] = self.cursor.joined[1]
        with self.assertRaisesRegex(verifier.VerificationFailure, "join differs"):
            self.run_check()
        self.assertNotIn("ZETARIS_REFERENCE_PARITY=PASS", self.output.getvalue())

    def test_driver_error_is_sanitised_and_resources_closed(self):
        self.cursor.failure = ".reporting_log LIMIT"
        with self.assertRaises(verifier.VerificationFailure) as error:
            self.run_check()
        self.assertNotIn("secret-password", str(error.exception))
        self.assertIn("reporting_log", str(error.exception))
        self.assertTrue(self.cursor.closed and self.connection.closed)

    def test_connect_failure_does_not_expose_credentials(self):
        def failing(*args):
            raise RuntimeError("password=hidden")
        self.connect = failing
        with self.assertRaises(verifier.VerificationFailure) as error:
            self.run_check()
        self.assertNotIn("hidden", str(error.exception))
        self.assertNotIn("ZETARIS_CONNECTION=PASS", self.output.getvalue())

    def test_defensive_row_cap_fails_without_successful_truncation(self):
        self.cursor.tables["facility_registry"] *= 400
        with self.assertRaisesRegex(verifier.VerificationFailure, "defensive cap"):
            self.run_check()
        self.assertNotIn("ZETARIS_SNAPSHOT=PASS", self.output.getvalue())
        self.assertTrue(self.cursor.closed and self.connection.closed)

    def test_early_cutoff_excludes_v2_but_hashes_full_snapshot(self):
        self.run_check("2025-12-06T00:00:00Z")
        self.assertIn("TARGET_RAW_TESTED=500", self.output.getvalue())
        self.assertIn("ZETARIS_MALARIA_MONTHLY_ROWS=145", self.output.getvalue())

    def test_queries_reject_injection_and_do_not_filter_stray_rows(self):
        for database in ("A.B", "A;DROP", "A --", "A JOIN x", "../evals"):
            with self.assertRaises(verifier.Blocked):
                verifier.source_queries(database, verifier.DEFAULT_DATASET)
        with self.assertRaises(verifier.Blocked):
            verifier.source_queries("A", "../evals")
        for query in verifier.source_queries("A", verifier.DEFAULT_DATASET).values():
            self.assertNotIn("WHERE", query)
            self.assertTrue(query.endswith("LIMIT 2001"))

    def test_native_strings_booleans_dates_and_nulls_normalise(self):
        table = "facility_registry"
        fields = [f for f, _ in verifier.SCHEMAS[table]]
        rows = [[r[f] for f in fields] for r in self.fixture[table]]
        from datetime import date
        rows[0][-2] = date(2024, 1, 1)
        rows[0][-1] = ""
        self.assertEqual(self.fixture[table], verifier.decode_rows(table, rows))
        with self.assertRaises(verifier.VerificationFailure):
            verifier.decode_rows(table, [["too", "short"]])

    def test_offline_mode_never_opens_jdbc_or_claims_live(self):
        with patch.object(verifier.importlib, "import_module", side_effect=AssertionError("No JVM")), redirect_stdout(self.output):
            result = verifier.main(["--check-fixture"])
        self.assertEqual(0, result)
        self.assertIn("SNAPSHOT_FIXTURE=PASS", self.output.getvalue())
        self.assertIn("ZETARIS_SNAPSHOT=NOT_RUN", self.output.getvalue())
        self.assertNotIn("ZETARIS_SNAPSHOT=PASS", self.output.getvalue())

    def test_missing_jar_is_blocked_before_login(self):
        with patch.dict(verifier.os.environ, {}, clear=True), redirect_stderr(self.output):
            result = verifier.main([])
        self.assertEqual(2, result)
        self.assertIn("ZETARIS_SNAPSHOT=BLOCKED", self.output.getvalue())

    def test_cli_read_failure_returns_fail_without_traceback(self):
        with patch.object(verifier, "load_snapshot", side_effect=ValueError("secret-data")), redirect_stderr(self.output):
            result = verifier.main(["--check-fixture"])
        self.assertEqual(1, result)
        self.assertNotIn("secret-data", self.output.getvalue())
        self.assertIn("SNAPSHOT_FIXTURE=FAIL", self.output.getvalue())


if __name__ == "__main__":
    unittest.main()
