from __future__ import annotations

import pytest

from sentinel.app import methods
from sentinel.app.container import AppContainer
from sentinel.app.registry import (
    BUSINESS_METHODS,
    EXPECTED_BUSINESS_METHOD_COUNT,
    register_all,
)
from sentinel.errors import InternalError
from sentinel.rpc import Dispatcher, RpcServer


def test_registers_exactly_thirty_eight_business_methods(container: AppContainer) -> None:
    dispatcher = Dispatcher()
    assert register_all(dispatcher, container) == EXPECTED_BUSINESS_METHOD_COUNT
    assert len(BUSINESS_METHODS) == 38
    assert set(dispatcher.methods()) == BUSINESS_METHODS


def test_total_is_forty_after_builtins(container: AppContainer) -> None:
    import io

    dispatcher = Dispatcher()
    register_all(dispatcher, container)
    RpcServer(io.BytesIO(), io.BytesIO(), dispatcher)
    assert len(dispatcher.methods()) == 40
    assert {"app.ping", "app.shutdown"} <= set(dispatcher.methods())


def test_duplicate_handler_fails_startup(container: AppContainer) -> None:
    dispatcher = Dispatcher()
    register_all(dispatcher, container)
    with pytest.raises(ValueError):
        register_all(dispatcher, container)


def test_missing_handler_fails_with_names(
    container: AppContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(methods.demo, "register", lambda dispatcher, c: None)
    with pytest.raises(InternalError) as caught:
        register_all(Dispatcher(), container)
    assert "demo.load" in str(caught.value.detail)
    assert "demo.clear" in str(caught.value.detail)


def test_extra_handler_is_rejected(
    container: AppContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    def extra(dispatcher: Dispatcher, c: AppContainer) -> None:
        from sentinel.rpc.builtins import EmptyParams, OkResult

        dispatcher.register(
            "demo.extra", lambda params, ctx: OkResult(ok=True), EmptyParams, OkResult
        )

    monkeypatch.setattr(methods.demo, "register", extra)
    with pytest.raises(InternalError) as caught:
        register_all(Dispatcher(), container)
    assert "demo.extra" in str(caught.value.detail)
