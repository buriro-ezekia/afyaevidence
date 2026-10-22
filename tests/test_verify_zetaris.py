"""Contract checks for the read-only registry access probe; no live JDBC claims."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import date
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_zetaris.py"
SPEC = importlib.util.spec_from_file_location("verify_zetaris", SCRIPT)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def rows():
    return list(probe.EXPECTED_ROWS)


class FakeCursor:
    def __init__(self, result):
        self.result = result
        self.statements = []
        self.closed = False

    def execute(self, sql):
        self.statements.append(sql)

    def fetchone(self):
        return (1,)

    def fetchmany(self, count):
        return self.result[:count]

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, result):
        self.handle = FakeCursor(result)
        self.closed = False

    def cursor(self):
        return self.handle

    def close(self):
        self.closed = True


class ProbeTests(unittest.TestCase):
    def test_committed_fixture_matches_fixed_probe_contract(self):
        self.assertEqual(probe.read_fixture(probe.DEFAULT_FIXTURE), rows())

    def test_rejects_identifiers_that_could_change_the_statement(self):
        for name in ("x", "a.b.c", "a.b;DROP TABLE x", "a.b --", "a. b", '"a".b', "a.b UNION SELECT 1"):
            with self.subTest(name=name), self.assertRaises(probe.Blocked):
                probe.build_query(name)

    def test_fixed_query_is_one_bounded_statement(self):
        sql = probe.build_query("AFYAEVIDENCE.facility_registry")
        self.assertTrue(sql.endswith("WHERE dataset_id = 'fx_probe_v1' LIMIT 7"))
        self.assertNotIn(";", sql)

    def test_reconciliation_retains_duplicates_and_missing_records(self):
        for actual in (rows()[:-1], rows() + rows()[:1], rows()[:-1] + rows()[:1]):
            with self.assertRaises(probe.VerificationFailure):
                probe.reconcile_rows(rows(), actual)

    def test_reconciliation_detects_changed_value(self):
        actual = rows()
        actual[0] = (*actual[0][:2], "D999", *actual[0][3:])
        with self.assertRaises(probe.VerificationFailure):
            probe.reconcile_rows(rows(), actual)

    def test_reconciliation_accepts_order_dates_and_nullable_end_date(self):
        actual = [(*row[:4], date(2024, 1, 1), "") for row in reversed(rows())]
        probe.reconcile_rows(rows(), actual)

    def test_required_missing_value_is_not_null_end_date(self):
        actual = rows()
        actual[0] = ("fx_probe_v1", "F001", None, "health_centre", "2024-01-01", None)
        with self.assertRaises(probe.VerificationFailure):
            probe.reconcile_rows(rows(), actual)

    def test_env_file_is_literal_and_does_not_override_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.local"
            path.write_text("# local only\nZETARIS_USERNAME='admin@zetaris.com'\nZETARIS_PASSWORD='$(touch unsafe)'\nUNCHANGED=file\n")
            environment = {"UNCHANGED": "existing"}
            probe.load_env_file(path, environment)
            self.assertEqual(environment["UNCHANGED"], "existing")
            self.assertEqual(environment["ZETARIS_PASSWORD"], "$(touch unsafe)")
            self.assertFalse((Path(directory) / "unsafe").exists())

    def test_malformed_env_does_not_leak_values_or_partially_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local.env"
            path.write_text("GOOD=secret\nINVALID secret-password\n")
            environment = {}
            with self.assertRaises(probe.Blocked) as raised:
                probe.load_env_file(path, environment)
            self.assertNotIn("secret", str(raised.exception))
            self.assertEqual(environment, {})

    def test_url_rejects_non_zetaris_or_extra_options(self):
        for url in ("jdbc:hive2://localhost:10000", "jdbc:zetaris:lightning@localhost:0", "jdbc:zetaris:lightning@localhost:10000;password=secret"):
            with self.assertRaises(probe.Blocked):
                probe.validate_url(url)
        self.assertEqual(probe.validate_url(probe.DEFAULT_URL), probe.DEFAULT_URL)

    def test_live_probe_executes_separate_reads_and_closes_resources(self):
        connection = FakeConnection(rows())
        calls = []
        def connect(*args):
            calls.append(args)
            return connection
        out = io.StringIO()
        with redirect_stdout(out):
            probe.check_live(connect, Path("/tmp/driver.jar"), probe.DEFAULT_URL, "admin@zetaris.com", "local-secret", probe.build_query("a.b"), rows())
        self.assertEqual(connection.handle.statements[0], "SELECT 1")
        self.assertEqual(len(connection.handle.statements), 2)
        self.assertEqual(calls[0][0], probe.DRIVER_CLASS)
        self.assertTrue(connection.closed and connection.handle.closed)
        self.assertIn("ZETARIS_PROJECT_TABLE=PASS", out.getvalue())
        self.assertNotIn("local-secret", out.getvalue())

    def test_mismatched_rows_never_emit_project_pass_and_still_close(self):
        connection = FakeConnection(rows()[:-1])
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(probe.VerificationFailure):
            probe.check_live(lambda *args: connection, Path("/tmp/driver.jar"), probe.DEFAULT_URL, "admin", "secret", probe.build_query("a.b"), rows())
        self.assertIn("ZETARIS_CONNECTION=PASS", out.getvalue())
        self.assertNotIn("ZETARIS_PROJECT_TABLE=PASS", out.getvalue())
        self.assertTrue(connection.closed and connection.handle.closed)

    def test_discovery_does_not_require_table_or_claim_project_pass(self):
        connection = FakeConnection([("AFYAEVIDENCE", "jdbc:secret://user:password@server")])
        connection.handle.description = [("name",), ("connection_url",)]
        out = io.StringIO()
        with redirect_stdout(out):
            probe.check_live(lambda *args: connection, Path("/tmp/driver.jar"), probe.DEFAULT_URL, "admin", "password", "", [], discover=True)
        self.assertEqual(connection.handle.statements, ["SELECT 1", "SHOW LIGHTNING DATABASES", "SHOW DATASOURCES"])
        self.assertIn("ZETARIS_DISCOVERY=PASS", out.getvalue())
        self.assertIn("ZETARIS_PROJECT_TABLE=NOT_RUN", out.getvalue())
        self.assertNotIn("jdbc:secret", out.getvalue())
        self.assertNotIn("ZETARIS_PROJECT_TABLE=PASS", out.getvalue())
        self.assertTrue(connection.closed and connection.handle.closed)

    def test_unavailable_connection_is_blocked_without_raw_credentials(self):
        def connect(*args):
            raise RuntimeError("user=admin password=secret-password")
        with self.assertRaises(probe.Blocked) as raised:
            probe.check_live(connect, Path("/tmp/driver.jar"), probe.DEFAULT_URL, "admin", "secret-password", probe.build_query("a.b"), rows())
        self.assertNotIn("secret-password", str(raised.exception))

    def test_fixture_only_mode_does_not_claim_live_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "registry.csv"
            fixture.write_text(",".join(probe.COLUMNS) + "\n" + "\n".join(",".join("" if value is None else value for value in row) for row in rows()) + "\n")
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                result = probe.main(["--check-fixture", "--fixture", str(fixture)])
            self.assertEqual(result, 0)
            self.assertIn("FIXTURE=PASS", out.getvalue())
            self.assertIn("ZETARIS_CONNECTION=NOT_RUN", out.getvalue())
            self.assertNotIn("ZETARIS_PROJECT_TABLE=PASS", out.getvalue())


if __name__ == "__main__":
    unittest.main()
