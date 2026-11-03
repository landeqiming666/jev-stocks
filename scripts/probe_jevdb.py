from __future__ import annotations

import argparse
import ipaddress
import json
import math
import multiprocessing
import os
import re
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendors" / "jevdb"))
from build import ROOT, sha256_file, valid_path, write_lock  # noqa: E402

DUCKDB_VERSION = "1.4.3"
LOAD_TIMEOUT_SEC = 30
CALL_TIMEOUT_SEC = 450
DEFAULT_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
CHILD_ENV_KEYS = ("JEV_API_KEY", "SENTINEL_OFFLINE", "SSL_CERT_FILE")
PROBE_CONFIG_KEYS = (*CHILD_ENV_KEYS, "JEV_ENDPOINT")
SETTINGS_SQL = (
    "SET jevdb_backend = 'jev'",
    "SET jevdb_model = 'jev-1.14.0'",
    "SET jevdb_threads = 4",
    "SET jevdb_max_retries = 3",
    "SET jevdb_retry_max_delay = 30",
    "SET jevdb_on_error = 'error'",
    "SET jevdb_timeout = 60",
    "SET threads = 1",
    "SET jevdb_retry_after_max = 30",
    "SET jevdb_dump_path = ''",
    "SET jevdb_raw_dump_path = ''",
)
PROBABILITY_SQL = (
    "SELECT jev_probability('The document supports the thesis', "
    "{'thesis': ?::VARCHAR}, {'document': ?::VARCHAR}), "
    "jev_holds('The document supports the thesis', "
    "{'thesis': ?::VARCHAR}, {'document': ?::VARCHAR})"
)
NULL_SQL = (
    "SELECT jev_probability('The review is positive', NULL::VARCHAR), "
    "jev_holds('The review is positive', NULL::VARCHAR)"
)
STATS_FIELDS = set(
    [
        "requests",
        "pairs",
        "records",
        "cache_hits",
        "input_tokens",
        "errors",
        "clients_created",
        "client_reuses",
        "request_ms",
        "send_ms",
        "cascade_requests",
        "cascade_items",
        "cascade_cache_hits",
        "calibration_items",
        "band_items",
        "cascade_errors",
        "cascade_input_tokens",
        "cascade_clients_created",
        "cascade_client_reuses",
        "cascade_request_ms",
        "cascade_send_ms",
        "cascade_last_low",
        "cascade_last_high",
        "candidate_left_rows",
        "candidate_right_rows",
        "candidate_left_retained",
        "candidate_right_retained",
        "index_posting_visits",
        "index_candidate_pairs",
        "cross_product_pairs",
        "retries",
        "cascade_retries",
    ]
)


def failure(error: Exception, *, loading: bool = False) -> dict:
    # 上游异常含响应正文；只保留错误类别和可辨认的 HTTP 状态。
    status = getattr(error, "status", getattr(error, "status_code", None))
    if status is None:
        match = re.search(r"\bHTTP[\s:(]+(\d{3})\b", str(error))
        status = int(match[1]) if match else None
    code = (
        "ENGINE_UNAVAILABLE"
        if loading
        else (
            "UNAUTHENTICATED"
            if status in (401, 403)
            else "RATE_LIMITED"
            if status == 429
            else "TIMEOUT"
            if isinstance(error, TimeoutError)
            else "MODEL_ERROR"
        )
    )
    data = {
        "status": "BLOCKED" if code == "UNAUTHENTICATED" else "FAILED",
        "error_code": code,
        "detail": "extension load failed" if loading else "semantic query failed",
    }
    if isinstance(status, int) and 100 <= status <= 599:
        data["http_status"] = status
    if loading and "symbol not found" in str(error):
        data["reason"] = "missing native DuckDB symbol"
    retry = getattr(error, "retry_after", None)
    if type(retry) in (int, float) and math.isfinite(retry) and 0 <= retry <= 300:
        data["retry_after_sec"] = retry
    return data


def initial_report(path: Path) -> dict:
    return {
        "build": {"status": "PASS" if path.is_file() else "FAILED"},
        "load": {"status": "FAILED"},
        "call": {"status": "BLOCKED"},
        "local": {"status": "SKIPPED"},
        "duckdb_version": DUCKDB_VERSION,
        "extension_sha256": sha256_file(path) if path.is_file() else "",
        "load_ms": 0,
        "request_id": None,
    }


def read_stats(con) -> dict:
    result = con.execute("SELECT * FROM jevdb_stats()")
    row = result.fetchone()
    if row is None:
        raise ValueError("missing stats row")
    return {
        column[0]: value
        for column, value in zip(result.description, row)
        if column[0] in STATS_FIELDS
        and (value is None or type(value) in (int, float) and math.isfinite(value))
    }


def endpoint_prefix(endpoint: str) -> str:
    try:
        if (
            not isinstance(endpoint, str)
            or len(endpoint) > 2048
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in endpoint)
            or "?" in endpoint
            or "#" in endpoint
        ):
            raise ValueError()
        parts = urlsplit(endpoint)
        host = parts.hostname
        port = parts.port
        if (
            parts.scheme != "https"
            or not host
            or len(host) > 253
            or "@" in parts.netloc
            or parts.netloc.endswith(":")
            or parts.path != "/v1/systemone"
            or port is not None
            and not 1 <= port <= 65535
        ):
            raise ValueError()
        if ":" in host:
            if "%" in host:
                raise ValueError()
            host = f"[{ipaddress.IPv6Address(host).compressed}]"
        elif all(label.isdigit() for label in host.split(".")):
            host = str(ipaddress.IPv4Address(host))
        elif any(
            not re.fullmatch(r"(?!-)[a-zA-Z0-9-]{1,63}(?<!-)", label) for label in host.split(".")
        ):
            raise ValueError()
        authority = host if port is None else f"{host}:{port}"
        return f"https://{authority}/v1/"
    except (ValueError, TypeError):
        raise ValueError("invalid JEV endpoint") from None


def run_probe(
    extension_path: Path,
    *,
    connect: Callable[..., object],
    env: Mapping[str, str],
    clock,
    on_loaded: Callable[[], None] | None = None,
) -> dict:
    path = valid_path(extension_path)
    report = initial_report(path)
    if not path.is_file():
        report["load"] = failure(FileNotFoundError(), loading=True)
        return report
    con = None
    timer = None
    started = clock()
    loaded = False
    try:
        if getattr(connect, "duckdb_version", DUCKDB_VERSION) != DUCKDB_VERSION:
            raise ValueError("DuckDB ABI mismatch")
        con = connect(":memory:", config={"allow_unsigned_extensions": "true"})

        def interrupt_load():
            with suppress(Exception):
                con.interrupt()

        timer = threading.Timer(LOAD_TIMEOUT_SEC, interrupt_load)
        timer.daemon = True
        timer.start()
        con.execute(f"LOAD '{path}'")
        elapsed = clock() - started
        timer.cancel()
        if elapsed >= LOAD_TIMEOUT_SEC:
            raise TimeoutError("extension load deadline exceeded")
        report["load_ms"] = max(0, int(elapsed * 1000))
        loaded = True
        report["load"] = {"status": "PASS"}
        if on_loaded:
            on_loaded()
        for sql in SETTINGS_SQL:
            con.execute(sql)
        keys = con.execute(
            "SELECT jev_keys_overlap(?::VARCHAR[], ?::VARCHAR[]), "
            "jev_keys_overlap(?::VARCHAR[], ?::VARCHAR[]), "
            "jev_keys_overlap(?::VARCHAR[], ?::VARCHAR[])",
            [["ZZAR"], ["ZZAR"], [], ["ZZAR"], None, ["ZZAR"]],
        ).fetchone()
        nulls = con.execute(NULL_SQL).fetchone()
        if keys != (True, False, True) or nulls != (None, None):
            raise ValueError("unexpected local function result")
        report["local"] = {
            "status": "PASS",
            "keys_overlap": list(keys),
            "null_probability": None,
            "null_holds": None,
        }
        if not env.get("JEV_API_KEY", "").strip():
            report["call"] = {
                "status": "BLOCKED",
                "error_code": "CONFIG_REQUIRED",
                "reason": "missing JEV_API_KEY; no remote query executed",
            }
            return report
        if env.get("SENTINEL_OFFLINE") == "1":
            report["call"] = {
                "status": "BLOCKED",
                "error_code": "SOURCE_UNAVAILABLE",
                "reason": "offline; no remote query executed",
            }
            return report
        try:
            endpoint = endpoint_prefix(env.get("JEV_ENDPOINT", DEFAULT_ENDPOINT))
        except ValueError:
            report["call"] = {
                "status": "FAILED",
                "error_code": "INVALID_ARGUMENT",
                "detail": "invalid JEV endpoint",
            }
            return report
        con.execute("SET jevdb_endpoint = ?", [endpoint])
        con.execute("CREATE SECRET jev (TYPE jev, PROVIDER env)")
        thesis = "Zenith Arc Robotics keeps research spending above 15 percent of revenue."
        document = "Zenith Arc Robotics reports research spending at 18 percent of revenue."
        row = con.execute(PROBABILITY_SQL, [thesis, document, thesis, document]).fetchone()
        if (
            row is None
            or len(row) != 2
            or type(row[0]) not in (int, float)
            or not math.isfinite(row[0])
            or not 0 <= row[0] <= 1
            or type(row[1]) is not bool
        ):
            raise ValueError("invalid probability or holds result")
        report["call"] = {"status": "PASS", "probability": row[0], "holds": row[1]}
    except Exception as error:
        report["call" if loaded else "load"] = failure(error, loading=not loaded)
        if not loaded:
            report["load_ms"] = max(0, int((clock() - started) * 1000))
        if loaded and report["local"]["status"] == "SKIPPED":
            report["local"] = {"status": "FAILED", "error_code": "MODEL_ERROR"}
    finally:
        if timer is not None:
            timer.cancel()
        if con is not None:
            if loaded:
                try:
                    report["stats"] = read_stats(con)
                except Exception:
                    report["stats_error"] = "stats unavailable"
                try:
                    con.execute("DROP SECRET IF EXISTS jev")
                except Exception:
                    report["cleanup_error"] = "temporary secret cleanup failed"
            try:
                con.close()
            except Exception:
                report["cleanup_error"] = "connection cleanup failed"
            if ("cleanup_error" in report or "stats_error" in report) and (
                report["call"]["status"] == "PASS"
            ):
                report["call"] = failure(ValueError("probe cleanup failed"))
    return report


def exit_code(report: dict) -> int:
    if report["build"]["status"] == "FAILED":
        return 3
    if report["load"]["status"] != "PASS":
        return 4
    if report["call"]["status"] == "BLOCKED":
        return 2
    return 0 if report["call"]["status"] == "PASS" else 1


def worker(path: Path, env: dict, channel) -> None:
    try:
        if multiprocessing.parent_process() is None:
            raise ValueError("worker requires an isolated child")
        # 映射缺省值也必须移除继承值，防止 native getenv 读取父进程另一把 key。
        for name in CHILD_ENV_KEYS:
            if name in env:
                os.environ[name] = env[name]
            else:
                os.environ.pop(name, None)
        import duckdb

        if duckdb.__version__ != DUCKDB_VERSION:
            report = initial_report(path)
            report["duckdb_version"] = duckdb.__version__
            report["load"] = failure(ValueError("DuckDB ABI mismatch"), loading=True)
        else:
            report = run_probe(
                path,
                connect=duckdb.connect,
                env=env,
                clock=time.monotonic,
                on_loaded=lambda: channel.send("loaded"),
            )
        channel.send(report)
    except Exception:
        report = initial_report(path)
        report["load"] = failure(ValueError("worker failed"), loading=True)
        channel.send(report)
    finally:
        channel.close()


def isolated_probe(path: Path, env: dict) -> dict:
    # 独立进程保证 connect/LOAD 卡死或 native 崩溃也能在 30 秒内退出。
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    config = {name: env[name] for name in PROBE_CONFIG_KEYS if name in env}
    process = context.Process(target=worker, args=(path, config, child), daemon=True)
    report = initial_report(path)
    loaded = False
    try:
        process.start()
        child.close()
        if not parent.poll(LOAD_TIMEOUT_SEC):
            raise TimeoutError()
        message = parent.recv()
        if message == "loaded":
            loaded = True
            report["load"] = {"status": "PASS"}
            if not parent.poll(CALL_TIMEOUT_SEC):
                raise TimeoutError()
            message = parent.recv()
        if not isinstance(message, dict):
            raise ValueError("invalid worker result")
        report = message
    except (TimeoutError, EOFError, OSError, ValueError) as error:
        report["call" if loaded else "load"] = failure(error, loading=not loaded)
    finally:
        if process.pid is not None:
            process.join(timeout=0.2)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
            process.close()
        parent.close()
        child.close()
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Isolated JEVDB build/LOAD/local/remote probe")
    parser.add_argument("--extension", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=ROOT / ".dev-data/jevdb/report.json")
    args = parser.parse_args(argv)
    try:
        path = valid_path(args.extension)
        output = args.report.resolve()
        output.relative_to((ROOT / ".dev-data/jevdb").resolve())
        output.parent.mkdir(parents=True, exist_ok=True)
        report = isolated_probe(path, dict(os.environ))
        write_lock(output, report)
        print(json.dumps(report, allow_nan=False))
        return exit_code(report)
    except (OSError, ValueError):
        print("PROBE FAILED: invalid local path or report destination", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
