from __future__ import annotations

import pytest

from sentinel.rpc import Dispatcher
from sentinel.rpc.builtins import EmptyParams

from .conftest import PipePair


def test_builtin_shutdown_returns_ok_before_stop(pipe_pair: PipePair) -> None:
    pipe_pair.request("shutdown", "app.shutdown")
    assert pipe_pair.wait_for_line() == {
        "jsonrpc": "2.0",
        "id": "shutdown",
        "result": {"ok": True},
    }
    pipe_pair.server.serve_forever()
    assert pipe_pair.server.stopped


@pytest.mark.parametrize("params", [{"force": "true"}, {"extra": True}, {"force": 1}])
def test_invalid_shutdown_params_do_not_stop_server(
    pipe_pair: PipePair, params: dict[str, object]
) -> None:
    pipe_pair.request("shutdown", "app.shutdown", params)
    assert pipe_pair.wait_for_line()["error"]["code"] == "INVALID_ARGUMENT"  # type: ignore[index]
    assert not pipe_pair.server.stopped
    pipe_pair.request("ping", "app.ping")
    assert pipe_pair.wait_for_line()["id"] == "ping"


def test_ping_rejects_extra_params(pipe_pair: PipePair) -> None:
    pipe_pair.request("ping", "app.ping", {"unexpected": True})
    assert pipe_pair.wait_for_line()["error"]["code"] == "INVALID_ARGUMENT"  # type: ignore[index]


def test_builtin_ping_uses_c00_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTINEL_CLOCK", "2026-11-02T00:00:00Z")
    pair = PipePair(Dispatcher())
    try:
        monkeypatch.setenv("SENTINEL_CLOCK", "2026-11-02T00:00:01Z")
        pair.request("ping", "app.ping")
        assert pair.wait_for_line()["result"] == {"ok": True, "uptimeMs": 1000}
    finally:
        pair.close()


def test_existing_builtin_registration_is_preserved() -> None:
    dispatcher = Dispatcher()
    dispatcher.register("app.ping", lambda p, c: {"custom": True}, EmptyParams)
    pair = PipePair(dispatcher)
    try:
        pair.request("ping", "app.ping")
        assert pair.wait_for_line()["result"] == {"custom": True}
    finally:
        pair.close()
