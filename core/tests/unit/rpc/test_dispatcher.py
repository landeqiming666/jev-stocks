from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ConfigDict, Field

from sentinel.errors import InternalError, UserError
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
    calls: list[str] = []

    def handler(params: BaseModel, ctx: RequestContext) -> dict[str, object]:
        calls.append(ctx.request_id)
        return {"quantity": 7}

    dispatcher.register("test.method", handler, QuantityParams, QuantityParams)
    response = dispatcher.dispatch(
        dispatcher.lookup("test.method"), {"quantity": quantity}, context()
    )
    assert response["error"] == UserError("INVALID_ARGUMENT", field="quantity").to_wire()
    assert calls == []


@pytest.mark.parametrize(
    "result",
    [
        {"quantity": "private result body"},
        {"quantity": True},
        {"quantity": 1.0},
        {},
        {"quantity": 7, "extra": "private result body"},
    ],
)
def test_valid_params_with_invalid_result_map_to_internal(
    result: dict[str, object],
    caplog: pytest.LogCaptureFixture,
) -> None:
    dispatcher = Dispatcher()
    calls: list[str] = []

    def handler(params: BaseModel, ctx: RequestContext) -> dict[str, object]:
        calls.append(ctx.request_id)
        return result

    dispatcher.register("test.method", handler, QuantityParams, QuantityParams)
    response = dispatcher.dispatch(
        dispatcher.lookup("test.method"),
        {"quantity": 7},
        context(),
    )
    assert calls == ["r-1"]
    assert response["error"] == InternalError(detail="ValidationError").to_wire("r-1")
    assert len(caplog.records) == 1
    assert vars(caplog.records[0])["sentinel"] == {
        "event": "rpc.dispatch.internal",
        "request_id": "r-1",
        "method": "test.method",
        "duration_ms": None,
        "error_code": "INTERNAL",
        "detail": "ValidationError",
    }
    assert "private result body" not in str(response)
    assert "private result body" not in caplog.text


def test_handler_raised_validation_error_is_internal() -> None:
    def handler(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return QuantityParams.model_validate({"quantity": "private result body"}, strict=True)

    dispatcher = Dispatcher()
    dispatcher.register("test.method", handler, QuantityParams, QuantityParams)
    response = dispatcher.dispatch(dispatcher.lookup("test.method"), {"quantity": 7}, context())
    assert response["error"] == InternalError(detail="ValidationError").to_wire("r-1")


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


@pytest.mark.parametrize("raw", [{"input_value": 7}, {"inputValue": 7, "input_value": 8}])
def test_wire_params_reject_python_names_before_handler(raw: dict[str, object]) -> None:
    class Params(BaseModel):
        model_config = ConfigDict(validate_by_alias=True, validate_by_name=True)
        input_value: int = Field(default=0, alias="inputValue")

    assert Params(input_value=7).input_value == 7
    calls: list[int] = []

    def handler(params: BaseModel, ctx: RequestContext) -> dict[str, object]:
        assert isinstance(params, Params)
        calls.append(params.input_value)
        return {"inputValue": params.input_value}

    dispatcher = Dispatcher()
    dispatcher.register("test.method", handler, Params, Params)
    accepted = dispatcher.dispatch(dispatcher.lookup("test.method"), {"inputValue": 7}, context())
    assert accepted["result"] == {"inputValue": 7}
    assert calls == [7]
    rejected = dispatcher.dispatch(dispatcher.lookup("test.method"), raw, context())
    assert rejected["error"] == UserError("INVALID_ARGUMENT", field="input_value").to_wire()
    assert calls == [7]


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


@pytest.mark.parametrize(
    "timeout",
    [
        True,
        False,
        0,
        -1,
        1.0,
        1.5,
        "30",
        None,
        float("nan"),
        float("inf"),
        -float("inf"),
    ],
)
def test_register_rejects_timeout_that_is_not_a_positive_integer(timeout: object) -> None:
    dispatcher = Dispatcher()
    with pytest.raises(ValueError, match="invalid method specification"):
        dispatcher.register("test.method", lambda p, c: {}, EmptyParams, timeout_ms=timeout)  # type: ignore[arg-type]
    assert dispatcher.methods() == ()


def test_invalid_timeout_cannot_replace_existing_registration() -> None:
    dispatcher = Dispatcher()
    dispatcher.register("test.method", lambda p, c: {}, EmptyParams, timeout_ms=1)
    original = dispatcher.lookup("test.method")
    with pytest.raises(ValueError):
        dispatcher.register(
            "test.method", lambda p, c: {}, EmptyParams, timeout_ms=True, replace=True
        )
    assert dispatcher.lookup("test.method") is original
    assert original is not None and original.timeout_ms == 1
