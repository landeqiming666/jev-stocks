from __future__ import annotations

import ctypes
import json
import multiprocessing
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
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


def native_env_worker_fixture(path, env, channel):
    native = ctypes.CDLL(None)
    native.getenv.argtypes = [ctypes.c_char_p]
    native.getenv.restype = ctypes.c_char_p

    def connect(*args, **kwargs):
        for name in ("JEV_API_KEY", "SENTINEL_OFFLINE", "SSL_CERT_FILE"):
            actual = native.getenv(name.encode())
            expected = env.get(name)
            if actual != (expected.encode() if expected is not None else None):
                raise ValueError("native child environment does not match caller")
        if os.environ.get("JEV_UNRELATED_TEST_SETTING") != "parent-only":
            raise ValueError("unrelated environment was overwritten")
        return FakeConnection()

    with patch.dict(sys.modules, {"duckdb": SimpleNamespace(__version__="1.4.3", connect=connect)}):
        probe.worker(path, env, channel)


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

    def test_endpoint_is_normalized_and_bound_before_secret_or_model(self):
        con = FakeConnection()
        report = self.run_fake(
            con, dict(self.env, JEV_ENDPOINT="https://Gateway.example:8443/v1/systemone")
        )
        bound = ("SET jevdb_endpoint = ?", ["https://gateway.example:8443/v1/"])
        self.assertIn(bound, con.calls)
        self.assertLess(
            con.calls.index(bound),
            con.calls.index(("CREATE SECRET jev (TYPE jev, PROVIDER env)", None)),
        )
        self.assertEqual(report["call"]["status"], "PASS")

    def test_endpoint_rejects_credentials_query_fragment_and_invalid_hosts(self):
        for endpoint in (
            "http://gateway.example/v1/systemone",
            "https://user:secret@gateway.example/v1/systemone",
            "https://gateway.example/v1/systemone?key=secret",
            "https://gateway.example/v1/systemone#secret",
            "https://gateway.example/v1/",
            "https://bad_host/v1/systemone",
            "https://-bad.example/v1/systemone",
            "https://gateway..example/v1/systemone",
            "https://256.0.0.1/v1/systemone",
            "https://gateway.example:70000/v1/systemone",
            "https://gateway.example:/v1/systemone",
            "https://gateway.example/v1/systemone\n",
            "https://gateway.example/v1/systemone?",
        ):
            con = FakeConnection()
            report = self.run_fake(con, dict(self.env, JEV_ENDPOINT=endpoint))
            with self.subTest(endpoint=endpoint):
                self.assertEqual(report["call"]["status"], "FAILED")
                self.assertEqual(report["call"]["error_code"], "INVALID_ARGUMENT")
                self.assertNotIn(endpoint, json.dumps(report))
                self.assertFalse(
                    any(
                        sql == probe.PROBABILITY_SQL or sql.startswith("CREATE SECRET")
                        for sql, _ in con.calls
                    )
                )
                self.assertTrue(con.closed)

    def test_missing_key_still_runs_local_even_with_bad_endpoint(self):
        con = FakeConnection()
        report = self.run_fake(
            con, {"JEV_ENDPOINT": "https://user:secret@gateway.example/v1/systemone"}
        )
        self.assertEqual(report["load"]["status"], "PASS")
        self.assertEqual(report["local"]["status"], "PASS")
        self.assertEqual(report["call"]["status"], "BLOCKED")
        self.assertNotIn("secret@gateway", json.dumps(report))

    def test_bound_endpoint_exception_does_not_echo_url_or_key(self):
        con = FakeConnection()
        original = con.execute
        endpoint = "https://secret-gateway.example/v1/systemone"

        def execute(sql, params=None):
            if sql == "SET jevdb_endpoint = ?":
                raise ValueError(endpoint + self.env["JEV_API_KEY"])
            return original(sql, params)

        con.execute = execute
        report = self.run_fake(con, dict(self.env, JEV_ENDPOINT=endpoint))
        self.assertEqual(report["call"]["status"], "FAILED")
        self.assertNotIn(endpoint, json.dumps(report))
        self.assertNotIn(self.env["JEV_API_KEY"], json.dumps(report))

    def run_native_env_child(self, env):
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=False)
        process = context.Process(target=native_env_worker_fixture, args=(self.path, env, child))
        try:
            process.start()
            child.close()
            self.assertTrue(parent.poll(10), "child did not respond")
            message = parent.recv()
            if message == "loaded":
                self.assertTrue(parent.poll(10), "child did not finish")
                message = parent.recv()
            return message
        finally:
            process.join(timeout=1)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
            process.close()
            parent.close()
            child.close()

    def test_caller_mapping_overrides_parent_key_offline_and_ca_only_in_child(self):
        inherited = {
            "JEV_API_KEY": "PARENT-KEY",
            "SENTINEL_OFFLINE": "1",
            "SSL_CERT_FILE": "/parent-ca.pem",
            "JEV_UNRELATED_TEST_SETTING": "parent-only",
        }
        mapping = dict(
            self.env,
            SENTINEL_OFFLINE="0",
            SSL_CERT_FILE="/mapping-ca.pem",
            JEV_UNRELATED_TEST_SETTING="ignored",
        )
        with patch.dict(os.environ, inherited):
            before = dict(os.environ)
            report = self.run_native_env_child(mapping)
            self.assertEqual(os.environ, before)
        self.assertEqual(report["call"]["status"], "PASS")
        self.assertNotIn("PARENT-KEY", json.dumps(report))
        self.assertNotIn(self.env["JEV_API_KEY"], json.dumps(report))

    def test_absent_mapping_removes_inherited_child_key_offline_and_ca(self):
        with patch.dict(
            os.environ,
            {
                "JEV_API_KEY": "PARENT-KEY",
                "SENTINEL_OFFLINE": "1",
                "SSL_CERT_FILE": "/parent-ca.pem",
                "JEV_UNRELATED_TEST_SETTING": "parent-only",
            },
        ):
            before = dict(os.environ)
            report = self.run_native_env_child({})
            self.assertEqual(os.environ, before)
        self.assertEqual(report["load"]["status"], "PASS")
        self.assertEqual(report["call"]["error_code"], "CONFIG_REQUIRED")


if __name__ == "__main__":
    unittest.main()
