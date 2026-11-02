from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, Field

from sentinel.errors import UserError
from sentinel.rpc import Dispatcher
from sentinel.rpc.builtins import EmptyParams
from sentinel.rpc.cancel import CancelToken
from sentinel.rpc.dispatcher import RequestContext


def context(method: str = "test.method") -> RequestContext:
    return RequestContext("r-1", method, CancelToken(), datetime(2026, 11, 2, tzinfo=UTC))


def test_unknown_method_maps_to_invalid_argument() -> None:
    dispatcher = Dispatcher()
    assert dispatcher.lookup("nope.method") is None
    response = dispatcher.dispatch(None, {}, context("nope.method"))
    assert response["error"] == UserError("INVALID_ARGUMENT", reason="UNKNOWN_METHOD").to_wire()


class QuantityParams(BaseModel):
    quantity: int


@pytest.mark.parametrize("quantity", ["7", True, 1.0])
def test_validation_error_reports_first_field(quantity: object) -> None:
    dispatcher = Dispatcher()
    dispatcher.register("test.method", lambda p, c: {}, QuantityParams)
    response = dispatcher.dispatch(
        dispatcher.lookup("test.method"), {"quantity": quantity}, context()
    )
    assert response["error"] == UserError("INVALID_ARGUMENT", field="quantity").to_wire()


def test_dispatcher_forbids_extra_fields_even_with_default_model_config() -> None:
    dispatcher = Dispatcher()
    dispatcher.register("test.method", lambda p, c: {}, QuantityParams)
    response = dispatcher.dispatch(
        dispatcher.lookup("test.method"), {"quantity": 7, "extra": 1}, context()
    )
    assert response["error"] == UserError("INVALID_ARGUMENT", field="extra").to_wire()


def test_result_models_serialize_aliases() -> None:
    class Result(BaseModel):
        request_id: str = Field(alias="requestId")

    dispatcher = Dispatcher()
    dispatcher.register(
        "test.method", lambda p, c: Result(requestId=c.request_id), EmptyParams, Result
    )
    assert dispatcher.dispatch(dispatcher.lookup("test.method"), {}, context())["result"] == {
        "requestId": "r-1",
    }


def test_internal_error_does_not_log_exception_body(caplog: pytest.LogCaptureFixture) -> None:
    def broken(params: BaseModel, ctx: RequestContext) -> dict[str, object]:
        raise RuntimeError("private user body")

    dispatcher = Dispatcher()
    dispatcher.register("test.method", broken, EmptyParams)
    response = dispatcher.dispatch(dispatcher.lookup("test.method"), {}, context())
    assert response["error"]["code"] == "INTERNAL"  # type: ignore[index]
    assert response["error"]["data"]["requestId"] == "r-1"  # type: ignore[index]
    assert "private user body" not in caplog.text
    assert "private user body" not in str(response)


@pytest.mark.parametrize("result", [{"bad": object()}, {"bad": float("nan")}, {"bad": "\ud800"}])
def test_unserializable_result_gets_internal_response(result: dict[str, object]) -> None:
    dispatcher = Dispatcher()
    dispatcher.register("test.method", lambda p, c: result, EmptyParams)
    response = dispatcher.dispatch(dispatcher.lookup("test.method"), {}, context())
    assert response["error"]["code"] == "INTERNAL"  # type: ignore[index]


def test_registration_validates_name_and_requires_explicit_replace() -> None:
    dispatcher = Dispatcher()

    def handler(params: BaseModel, ctx: RequestContext) -> dict[str, object]:
        return {}

    with pytest.raises(ValueError):
        dispatcher.register("invalid", handler, EmptyParams)
    dispatcher.register("test.method", handler, EmptyParams)
    with pytest.raises(ValueError):
        dispatcher.register("test.method", handler, EmptyParams)
    dispatcher.register("test.method", handler, EmptyParams, replace=True)
    assert dispatcher.methods() == ("test.method",)
    assert dispatcher.lookup("test.method").cancellable is False  # type: ignore[union-attr]
