from __future__ import annotations

from sentinel.demo import DemoService
from sentinel.demo.rpc import register_handlers
from sentinel.rpc import CancelToken, Dispatcher
from sentinel.rpc.dispatcher import RequestContext
from sentinel.storage import Database

from .conftest import NOW, RESOURCES


def call(dispatcher: Dispatcher, method: str, params: dict[str, object]) -> dict[str, object]:
    return dispatcher.dispatch(
        dispatcher.lookup(method),
        params,
        RequestContext(f"r-{method}", method, CancelToken(), NOW),
    )


def test_rpc_load_result_matches_contract(db: Database) -> None:
    dispatcher = Dispatcher()
    register_handlers(dispatcher, DemoService(db, RESOURCES, lambda: NOW))
    response = call(dispatcher, "demo.load", {})
    assert response["result"] == {
        "loaded": True,
        "counts": {
            "instruments": 6,
            "holdings": 5,
            "theses": 6,
            "events": 6,
            "decisions": 12,
            "prices": 1560,
        },
    }
    cleared = call(dispatcher, "demo.clear", {})
    assert cleared["result"] == {"ok": True}
    again = call(dispatcher, "demo.clear", {})
    assert again["result"] == {"ok": True}


def test_rpc_load_twice_reports_conflict(db: Database) -> None:
    dispatcher = Dispatcher()
    register_handlers(dispatcher, DemoService(db, RESOURCES, lambda: NOW))
    assert call(dispatcher, "demo.load", {})["result"]["loaded"] is True
    error = call(dispatcher, "demo.load", {})["error"]
    assert error["code"] == "CONFLICT"
    assert error["data"]["reason"] == "ALREADY_LOADED"
