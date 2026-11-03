from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import probe_jevdb as probe  # noqa: E402


class FakeConnection:
    def __init__(self, error=None, load_error=None, probability=0.7):
        self.calls = []
        self.error = error
        self.load_error = load_error
        self.probability = probability
        self.closed = False
        self.description = []
        self.row = None

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if sql.startswith("LOAD") and self.load_error:
            raise self.load_error
        if "NULL::VARCHAR" in sql:
            self.row = (None, None)
        elif sql.startswith("SELECT jev_probability"):
            if self.error:
                raise self.error
            self.row = (self.probability, True)
        elif sql.startswith("SELECT jev_keys_overlap"):
            self.row = (True, False, True)
        elif sql == "SELECT * FROM jevdb_stats()":
            self.description = [("requests",), ("retries",), ("api_key",)]
            self.row = (0, 0, "TEST-KEY-DO-NOT-LOG")
        return self

    def fetchone(self):
        return self.row

    def interrupt(self):
        pass

    def close(self):
        self.closed = True


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jev probe space ")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name).resolve() / "jevdb.duckdb_extension"
        self.path.write_bytes(b"fake-test-artifact")
        self.env = {"JEV_API_KEY": "TEST-KEY-DO-NOT-LOG"}

    def run_fake(self, con, env=None):
        def connect(database, config):
            self.assertEqual(database, ":memory:")
            self.assertEqual(config, {"allow_unsigned_extensions": "true"})
            return con

        return probe.run_probe(
            self.path, connect=connect, env=self.env if env is None else env, clock=time.monotonic
        )

    def test_probe_sets_required_jevdb_settings(self):
        con = FakeConnection()
        report = self.run_fake(con)
        for setting in probe.SETTINGS_SQL:
            self.assertIn((setting, None), con.calls)
        self.assertIn(("SET jevdb_on_error = 'error'", None), con.calls)
        self.assertEqual(report["call"]["status"], "PASS")
        self.assertIn(("CREATE SECRET jev (TYPE jev, PROVIDER env)", None), con.calls)
        self.assertIn(("DROP SECRET IF EXISTS jev", None), con.calls)
        self.assertTrue(con.closed)

    def test_probe_401_is_blocked_not_passed(self):
        report = self.run_fake(FakeConnection(error=RuntimeError("HTTP 401")))
        self.assertEqual(report["call"]["status"], "BLOCKED")
        self.assertEqual(report["call"]["error_code"], "UNAUTHENTICATED")
        self.assertEqual(probe.exit_code(report), 2)

    def test_probe_query_error_is_not_treated_as_false(self):
        for error, code in (
            ("MODEL_ERROR", "MODEL_ERROR"),
            ("HTTP 429", "RATE_LIMITED"),
            ("HTTP 503", "MODEL_ERROR"),
            ("HTTP 403", "UNAUTHENTICATED"),
        ):
            con = FakeConnection(error=RuntimeError(error))
            report = self.run_fake(con)
            self.assertEqual(report["call"]["error_code"], code)
            self.assertNotIn("probability", report["call"])
            self.assertNotIn("holds", report["call"])
            self.assertEqual(
                report["call"]["status"], "BLOCKED" if code == "UNAUTHENTICATED" else "FAILED"
            )
            self.assertTrue(con.closed)

    def test_probe_report_does_not_contain_key(self):
        error = RuntimeError("HTTP 401 Authorization: Bearer TEST-KEY-DO-NOT-LOG body=secret")
        report = self.run_fake(FakeConnection(error=error))
        text = json.dumps(report)
        for forbidden in (self.env["JEV_API_KEY"], "Authorization", "body=secret", "api_key"):
            self.assertNotIn(forbidden, text)

    def test_missing_key_blocks_remote_but_runs_local_functions(self):
        con = FakeConnection()
        report = self.run_fake(con, {})
        self.assertEqual(report["load"]["status"], "PASS")
        self.assertEqual(report["call"]["status"], "BLOCKED")
        self.assertEqual(report["call"]["error_code"], "CONFIG_REQUIRED")
        self.assertEqual(report["local"]["status"], "PASS")
        self.assertFalse(any(s.startswith("CREATE SECRET") for s, _ in con.calls))
        self.assertFalse(
            any(
                s.startswith("SELECT jev_probability") and "NULL::VARCHAR" not in s
                for s, _ in con.calls
            )
        )
        self.assertTrue(con.closed)

    def test_abi_load_failure_has_exit_four_and_closes(self):
        con = FakeConnection(load_error=RuntimeError("ABI mismatch TEST-KEY-DO-NOT-LOG"))
        report = self.run_fake(con)
        self.assertEqual(report["load"]["status"], "FAILED")
        self.assertEqual(probe.exit_code(report), 4)
        self.assertTrue(con.closed)
        self.assertNotIn(self.env["JEV_API_KEY"], json.dumps(report))

    def test_path_spaces_allowed_quotes_nul_and_newlines_rejected(self):
        con = FakeConnection()
        self.run_fake(con, {})
        self.assertIn((f"LOAD '{self.path}'", None), con.calls)
        for bad in ("a'b", 'a"b', "a\x00b", "a\nb", "a\rb"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                probe.run_probe(
                    Path(bad),
                    connect=lambda **kw: self.fail("connected"),
                    env={},
                    clock=time.monotonic,
                )

    def test_nonfinite_out_of_range_null_and_boolean_probability_fail(self):
        for probability in (float("nan"), float("inf"), -0.1, 1.1, None, True):
            report = self.run_fake(FakeConnection(probability=probability))
            self.assertEqual(report["call"]["status"], "FAILED")
            self.assertNotIn("probability", report["call"])

    def test_cleanup_after_secret_and_stats_errors(self):
        con = FakeConnection()
        original = con.execute

        def execute(sql, params=None):
            if sql.startswith("CREATE SECRET") or "jevdb_stats" in sql:
                raise RuntimeError("TEST-KEY-DO-NOT-LOG")
            return original(sql, params)

        con.execute = execute
        report = self.run_fake(con)
        self.assertEqual(report["call"]["status"], "FAILED")
        self.assertTrue(con.closed)
        self.assertIn(("DROP SECRET IF EXISTS jev", None), con.calls)
        self.assertNotIn(self.env["JEV_API_KEY"], json.dumps(report))

    def test_load_deadline_is_not_a_success(self):
        with patch.object(probe, "LOAD_TIMEOUT_SEC", 0):
            report = self.run_fake(FakeConnection())
        self.assertEqual(report["load"]["status"], "FAILED")
        self.assertEqual(probe.exit_code(report), 4)

    def test_connect_failure_and_wrong_version_do_not_query(self):
        def connect(*args, **kwargs):
            raise RuntimeError("TEST-KEY-DO-NOT-LOG")

        report = probe.run_probe(self.path, connect=connect, env=self.env, clock=time.monotonic)
        self.assertEqual(probe.exit_code(report), 4)
        connect.duckdb_version = "1.4.2"
        report = probe.run_probe(self.path, connect=connect, env=self.env, clock=time.monotonic)
        self.assertEqual(probe.exit_code(report), 4)
        self.assertNotIn(self.env["JEV_API_KEY"], json.dumps(report))

    def test_offline_with_key_does_not_issue_semantic_request(self):
        con = FakeConnection()
        report = self.run_fake(con, dict(self.env, SENTINEL_OFFLINE="1"))
        self.assertEqual(probe.exit_code(report), 2)
        self.assertEqual(report["call"]["error_code"], "SOURCE_UNAVAILABLE")
        self.assertFalse(any(sql == probe.PROBABILITY_SQL for sql, _ in con.calls))

    def test_local_function_failure_is_reported_and_cleaned_up(self):
        con = FakeConnection()
        original = con.execute

        def execute(sql, params=None):
            result = original(sql, params)
            if sql.startswith("SELECT jev_keys_overlap"):
                result.row = (False, False, False)
            return result

        con.execute = execute
        report = self.run_fake(con, {})
        self.assertEqual(report["local"]["status"], "FAILED")
        self.assertEqual(report["call"]["status"], "FAILED")
        self.assertTrue(con.closed)

    def test_cli_has_hard_process_load_timeout(self):
        with patch.object(probe, "LOAD_TIMEOUT_SEC", 0):
            report = probe.isolated_probe(self.path, {})
        self.assertEqual(probe.exit_code(report), 4)

    def test_retry_after_is_bounded_and_native_error_body_is_removed(self):
        error = RuntimeError("HTTP 429 TEST-KEY-DO-NOT-LOG body=secret")
        error.retry_after = 12
        report = self.run_fake(FakeConnection(error=error))
        self.assertEqual(report["call"]["retry_after_sec"], 12)
        error.retry_after = float("inf")
        report = self.run_fake(FakeConnection(error=error))
        self.assertNotIn("retry_after_sec", report["call"])
        self.assertNotIn(self.env["JEV_API_KEY"], json.dumps(report))


if __name__ == "__main__":
    unittest.main()
