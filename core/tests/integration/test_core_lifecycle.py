"""真实核心进程的生命周期、错误映射与取消。"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from sentinel.rpc import Dispatcher, RpcServer
from sentinel.rpc.builtins import EmptyParams, OkResult
from tests.integration.harness import CoreHarness


def test_core_ready_then_bootstrap(core: CoreHarness) -> None:
    boot = core.result("app.bootstrap")
    assert str(boot["protocolVersion"]).startswith("1.")
    assert boot["platform"] in ("macos", "windows")
    assert boot["demoDataLoaded"] is False
    assert boot["offline"] is True
    assert boot["engine"]["active"] is None
    assert boot["configured"] == {"jevKey": False, "secEmail": False}


def test_spaces_and_chinese_path(core: CoreHarness, data_dir: Path) -> None:
    assert "空格" in str(data_dir)
    assert (data_dir / "logs" / "core.jsonl").is_file()
    assert (data_dir / "sentinel.duckdb").is_file()


def test_unknown_method_and_bad_params_are_invalid_argument(core: CoreHarness) -> None:
    unknown = core.request("no.such.method")
    assert unknown["error"]["code"] == "INVALID_ARGUMENT"
    assert unknown["error"]["message"]

    bad = core.request("paper.order.place", {"accountId": "x", "side": "hold"})
    assert bad["error"]["code"] == "INVALID_ARGUMENT"
    assert isinstance(bad["error"]["data"]["field"], str) and bad["error"]["data"]["field"]


def test_shutdown_exits_within_three_seconds(core: CoreHarness) -> None:
    started = time.monotonic()
    response = core.request("app.shutdown")
    assert response["result"] == {"ok": True}
    deadline = started + 3.0
    while core.poll() is None:
        if time.monotonic() > deadline:
            raise AssertionError("core did not exit within 3s")
        time.sleep(0.02)


def test_cancel_returns_within_200ms(core: CoreHarness) -> None:
    """对真实核心的可取消方法发起取消；离线时该请求通常立即结束。"""
    core.result("demo.load")
    history = core.result("scan.history", {"limit": 5})
    run_id = history["items"][0]["runId"]
    detail = core.result("scan.detail", {"runId": run_id})
    failed = [batch for batch in detail["batches"] if batch["status"] == "failed"]
    if not failed:
        pytest.skip("demo run has no failed batch to retry")

    started = time.monotonic()
    request_id = core.send(
        {
            "jsonrpc": "2.0",
            "id": "r-cancel",
            "method": "scan.retryBatch",
            "params": {"batchId": failed[0]["batchId"]},
        }
    )
    core.cancel(request_id)
    response = core.wait_response(request_id, 5)
    elapsed_ms = (time.monotonic() - started) * 1000
    assert elapsed_ms <= 2000
    if response.get("error", {}).get("code") == "CANCELLED":
        assert elapsed_ms <= 200
    else:
        pytest.skip("retry finished before cancel; 200ms bound needs a slow external call")


def test_cancel_deadline_on_real_server() -> None:
    """真实 RpcServer + 慢处理器：取消必须在 200ms 内返回 CANCELLED。"""
    import io
    import json
    import os

    dispatcher = Dispatcher()

    def slow(params: object, ctx: object) -> OkResult:
        time.sleep(2.0)
        return OkResult(ok=True)

    dispatcher.register("test.slow", slow, EmptyParams, OkResult, cancellable=True)
    read_fd, write_fd = os.pipe()
    stdin = os.fdopen(read_fd, "rb", buffering=0)
    stdout = io.BytesIO()
    server = RpcServer(stdin, stdout, dispatcher, on_start=None)
    server.start()
    try:
        os.write(
            write_fd,
            json.dumps(
                {"jsonrpc": "2.0", "id": "r-01", "method": "test.slow", "params": {}}
            ).encode()
            + b"\n",
        )
        time.sleep(0.2)
        started = time.monotonic()
        os.write(
            write_fd,
            json.dumps({"jsonrpc": "2.0", "method": "$/cancel", "params": {"id": "r-01"}}).encode()
            + b"\n",
        )
        while time.monotonic() - started < 1.0:
            if b"CANCELLED" in stdout.getvalue():
                break
            time.sleep(0.01)
        elapsed_ms = (time.monotonic() - started) * 1000
    finally:
        os.close(write_fd)
        server.stop()
        stdin.close()
    assert b'"code":"CANCELLED"' in stdout.getvalue()
    assert elapsed_ms <= 200


def test_stderr_has_no_traceback_on_clean_exit(core: CoreHarness) -> None:
    core.result("app.bootstrap")
    core.stop()
    assert "Traceback" not in core.stderr()


def test_response_ids_are_echoed(core: CoreHarness) -> None:
    response = core.request("app.ping")
    assert response["id"] == "r-01"
    assert response["result"]["ok"] is True
