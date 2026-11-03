import json
from decimal import Decimal

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from sentinel.portfolio import PortfolioService, register_handlers
from sentinel.portfolio.models import HoldingUpsertParams, ThesisUpdateParams
from sentinel.rpc import CancelToken, Dispatcher
from sentinel.rpc.dispatcher import RequestContext
from sentinel.storage import Database

from .conftest import NOW, ROOT, add_downstream, query

METHODS = (
    "holdings.list",
    "holdings.upsert",
    "holdings.archive",
    "thesis.list",
    "thesis.create",
    "thesis.update",
    "thesis.archive",
    "thesis.versions",
)
CONTRACTS = ROOT / "contracts"
TYPES = json.loads((CONTRACTS / "types.schema.json").read_text())
REGISTRY = Registry().with_resource(
    "types.schema.json", Resource.from_contents(TYPES, default_specification=DRAFT202012)
)


class Contract:
    def __init__(self, method: str) -> None:
        self.document = json.loads((CONTRACTS / "methods" / (method + ".json")).read_text())
        self.params = Draft202012Validator(self.document["params"], registry=REGISTRY)
        self.result = Draft202012Validator(
            self.document["result"], registry=REGISTRY, format_checker=FormatChecker()
        )
        self.error = Draft202012Validator(
            {"$ref": "types.schema.json#/$defs/RpcError"}, registry=REGISTRY
        )

    def response(self, response: dict) -> None:
        assert response["jsonrpc"] == "2.0" and response["id"] == "r-p01"
        if "result" in response:
            self.result.validate(response["result"])
        else:
            self.error.validate(response["error"])


@pytest.fixture
def dispatcher(service: PortfolioService) -> Dispatcher:
    dispatcher = Dispatcher()
    register_handlers(dispatcher, service)
    return dispatcher


def call(dispatcher: Dispatcher, method: str, params: dict) -> dict:
    response = dispatcher.dispatch(
        dispatcher.lookup(method), params, RequestContext("r-p01", method, CancelToken(), NOW)
    )
    return json.loads(json.dumps(response, allow_nan=False))


@pytest.mark.parametrize("method", METHODS)
def test_eight_registered_models_roundtrip_all_contract_examples(
    dispatcher: Dispatcher, method: str
) -> None:
    contract = Contract(method)
    spec = dispatcher.lookup(method)
    assert spec is not None and spec.result_model is not None
    for example in contract.document["examples"]:
        if "result" in example:
            contract.params.validate(example["params"])
            spec.params_model.model_validate(
                example["params"], strict=True, extra="forbid", by_alias=True, by_name=False
            )
            parsed = spec.result_model.model_validate(
                example["result"], strict=True, extra="forbid"
            )
            assert parsed.model_dump(mode="json", by_alias=True) == example["result"]
        else:
            contract.error.validate(example["error"])


@pytest.mark.parametrize("method", METHODS)
def test_eight_actual_handlers_and_schema_success_errors(
    dispatcher: Dispatcher, service: PortfolioService, method: str
) -> None:
    assert set(dispatcher.methods()) == set(METHODS)
    service.upsert_holding("us:ZZAR", Decimal("1"), None, None)
    first = service.create_thesis("us:ZZAR", "First", None)
    params = {
        "holdings.list": {},
        "holdings.upsert": {"instrumentId": "us:ZZAR", "quantity": "2", "avgCost": "12.50"},
        "holdings.archive": {"instrumentId": "us:ZZAR"},
        "thesis.list": {"instrumentId": "us:ZZAR", "status": "active"},
        "thesis.create": {"instrumentId": "us:ZZAR", "statement": "Second"},
        "thesis.update": {
            "thesisId": first.thesis_id,
            "statement": "Changed",
            "expectedVersion": 1,
        },
        "thesis.archive": {"thesisId": first.thesis_id},
        "thesis.versions": {"thesisId": first.thesis_id},
    }[method]
    contract = Contract(method)
    contract.params.validate(params)
    response = call(dispatcher, method, params)
    assert "result" in response
    contract.response(response)
    unknown = params | {"unknown": "private-input"}
    assert not contract.params.is_valid(unknown)
    rejected = call(dispatcher, method, unknown)
    contract.response(rejected)
    assert rejected["error"]["code"] == "INVALID_ARGUMENT"
    assert rejected["error"]["data"]["field"] == "unknown"


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        1,
        1.5,
        -1,
        "-1",
        "0.00001",
        "1.00000",
        "NaN",
        "Infinity",
        "1e3",
        "01",
        "1.",
        " 1",
        "100000000000000",
    ],
)
@pytest.mark.parametrize("field", ["quantity", "avgCost"])
def test_wire_amount_rejects_noncanonical_input(
    dispatcher: Dispatcher, db: Database, value: object, field: str
) -> None:
    params = {"instrumentId": "us:ZZAR", "quantity": "1", field: value}
    contract = Contract("holdings.upsert")
    assert not contract.params.is_valid(params)
    response = call(dispatcher, "holdings.upsert", params)
    contract.response(response)
    assert response["error"]["code"] == "INVALID_ARGUMENT"
    assert response["error"]["data"]["field"] == field
    assert query(db, "SELECT count(*) FROM holding") == [(0,)]


@pytest.mark.parametrize("value", ["0", "0.0000", "1", "1.2", "99999999999999.9999"])
def test_wire_amount_accepts_full_decimal_range(dispatcher: Dispatcher, value: str) -> None:
    params = {"instrumentId": "us:ZZAR", "quantity": value}
    contract = Contract("holdings.upsert")
    contract.params.validate(params)
    response = call(dispatcher, "holdings.upsert", params)
    assert "result" in response
    contract.response(response)
    assert Decimal(response["result"]["quantity"]) == Decimal(value)


@pytest.mark.parametrize("field", ["quantity", "avgCost"])
def test_wire_decimal_string_rejects_trailing_newline(
    dispatcher: Dispatcher, db: Database, field: str
) -> None:
    params = {"instrumentId": "us:ZZAR", "quantity": "1", field: "1\n"}
    contract = Contract("holdings.upsert")
    assert not contract.params.is_valid(params)
    response = call(dispatcher, "holdings.upsert", params)
    contract.response(response)
    assert response["error"]["code"] == "INVALID_ARGUMENT"
    assert response["error"]["data"]["field"] == field
    assert query(db, "SELECT count(*) FROM holding") == [(0,)]


@pytest.mark.parametrize(
    "method,params,field",
    [
        ("holdings.upsert", {"instrument_id": "us:ZZAR", "quantity": "1"}, "instrumentId"),
        ("holdings.archive", {"instrument_id": "us:ZZAR"}, "instrumentId"),
        ("thesis.list", {"instrument_id": "us:ZZAR"}, "instrument_id"),
        ("thesis.create", {"instrument_id": "us:ZZAR", "statement": "First"}, "instrumentId"),
        (
            "thesis.update",
            {"thesis_id": "missing", "statement": "First", "expectedVersion": 1},
            "thesisId",
        ),
        ("thesis.archive", {"thesis_id": "missing"}, "thesisId"),
        ("thesis.versions", {"thesis_id": "missing"}, "thesisId"),
        (
            "holdings.upsert",
            {"instrumentId": "us:ZZAR", "quantity": "1", "avg_cost": "2"},
            "avg_cost",
        ),
        (
            "thesis.create",
            {"instrumentId": "us:ZZAR", "statement": "First", "kill_condition": "Floor"},
            "kill_condition",
        ),
        (
            "thesis.update",
            {"thesisId": "missing", "statement": "First", "expected_version": 1},
            "expectedVersion",
        ),
    ],
)
def test_real_dispatcher_rejects_snake_case_but_internal_models_allow_it(
    dispatcher: Dispatcher, method: str, params: dict, field: str
) -> None:
    assert not Contract(method).params.is_valid(params)
    spec = dispatcher.lookup(method)
    spec.params_model.model_validate(params)
    response = call(dispatcher, method, params)
    Contract(method).response(response)
    assert response["error"]["code"] == "INVALID_ARGUMENT"
    assert response["error"]["data"]["field"] == field


@pytest.mark.parametrize("value", [True, False, "1", 1.0, 0, -1, None])
def test_expected_version_requires_positive_strict_int(
    dispatcher: Dispatcher, value: object
) -> None:
    params = {"thesisId": "missing", "statement": "First", "expectedVersion": value}
    response = call(dispatcher, "thesis.update", params)
    Contract("thesis.update").response(response)
    assert response["error"]["code"] == "INVALID_ARGUMENT"
    assert response["error"]["data"]["field"] == "expectedVersion"


def test_missing_expected_version_is_invalid_argument(dispatcher: Dispatcher) -> None:
    response = call(dispatcher, "thesis.update", {"thesisId": "missing", "statement": "First"})
    assert response["error"]["data"]["field"] == "expectedVersion"


@pytest.mark.parametrize(
    "params,field",
    [
        ({"instrumentId": None}, "instrumentId"),
        ({"status": None}, "status"),
        ({"status": "all"}, "status"),
    ],
)
def test_optional_thesis_filters_forbid_explicit_null_and_invalid_enum(
    dispatcher: Dispatcher, params: dict, field: str
) -> None:
    contract = Contract("thesis.list")
    assert not contract.params.is_valid(params)
    response = call(dispatcher, "thesis.list", params)
    contract.response(response)
    assert response["error"]["data"]["field"] == field


@pytest.mark.parametrize("field,maximum", [("statement", 500), ("killCondition", 300)])
def test_unicode_text_wire_boundaries_match_schema(
    dispatcher: Dispatcher, field: str, maximum: int
) -> None:
    params = {
        "instrumentId": "us:ZZAR",
        "statement": "First",
        field: "\u3000" + "😀" * maximum + "\x1c",
    }
    contract = Contract("thesis.create")
    assert contract.params.is_valid(params)
    response = call(dispatcher, "thesis.create", params)
    assert "result" in response
    contract.response(response)
    assert response["result"][field] == "😀" * maximum
    params[field] = "😀" * (maximum + 1)
    assert not contract.params.is_valid(params)
    response = call(dispatcher, "thesis.create", params)
    contract.response(response)
    assert response["error"]["data"]["field"] == field


def test_note_strip_boundary_and_blank_normalization(dispatcher: Dispatcher) -> None:
    params = {"instrumentId": "us:ZZAR", "quantity": "1", "note": "\u3000" + "😀" * 200 + "\x1c"}
    contract = Contract("holdings.upsert")
    contract.params.validate(params)
    response = call(dispatcher, "holdings.upsert", params)
    contract.response(response)
    assert response["result"]["note"] == "😀" * 200
    params["note"] = " \n "
    assert call(dispatcher, "holdings.upsert", params)["result"]["note"] is None
    params["note"] = "😀" * 201
    assert call(dispatcher, "holdings.upsert", params)["error"]["data"]["field"] == "note"


@pytest.mark.parametrize(
    "method,params",
    [
        ("holdings.upsert", {"instrumentId": "us:ABSENT", "quantity": "1"}),
        ("holdings.archive", {"instrumentId": "us:ABSENT"}),
        ("thesis.create", {"instrumentId": "us:ABSENT", "statement": "First"}),
        ("thesis.update", {"thesisId": "missing", "statement": "First", "expectedVersion": 1}),
        ("thesis.archive", {"thesisId": "missing"}),
        ("thesis.versions", {"thesisId": "missing"}),
    ],
)
def test_real_handler_not_found_errors_match_contract(
    dispatcher: Dispatcher, method: str, params: dict
) -> None:
    response = call(dispatcher, method, params)
    Contract(method).response(response)
    assert response["error"]["code"] == "NOT_FOUND"


def test_conflict_and_active_limit_error_data(
    dispatcher: Dispatcher, service: PortfolioService
) -> None:
    first = service.create_thesis("us:ZZAR", "First", None)
    service.update_thesis(first.thesis_id, "Second", None, 1)
    response = call(
        dispatcher,
        "thesis.update",
        {"thesisId": first.thesis_id, "statement": "Second", "expectedVersion": 1},
    )
    Contract("thesis.update").response(response)
    assert (
        response["error"]["code"] == "CONFLICT" and response["error"]["data"]["currentVersion"] == 2
    )
    for i in range(4):
        service.create_thesis("us:ZZAR", str(i), None)
    response = call(dispatcher, "thesis.create", {"instrumentId": "us:ZZAR", "statement": "Sixth"})
    Contract("thesis.create").response(response)
    assert (
        response["error"]["data"]["max"] == 5
        and response["error"]["data"]["field"] == "instrumentId"
    )


def test_invalid_result_is_internal_and_has_request_id(service: PortfolioService) -> None:
    dispatcher = Dispatcher()
    register_handlers(dispatcher, service)
    spec = dispatcher.lookup("holdings.list")

    def broken(params: BaseModel, ctx: RequestContext) -> dict[str, object]:
        return {"items": "invalid-output", "asOf": "invalid"}

    dispatcher.register(spec.method, broken, spec.params_model, spec.result_model, replace=True)
    response = call(dispatcher, "holdings.list", {})
    Contract("holdings.list").response(response)
    assert response["error"]["code"] == "INTERNAL"
    assert response["error"]["data"]["requestId"] == "r-p01"
    assert "invalid-output" not in str(response)


def test_internal_models_accept_snake_case_decimal_properties() -> None:
    holding = HoldingUpsertParams(
        instrument_id="us:ZZAR", quantity=Decimal("1"), avg_cost=Decimal("2")
    )
    assert holding.avg_cost == Decimal("2.0000")
    assert (
        ThesisUpdateParams(
            thesis_id="missing", statement="First", expected_version=1
        ).expected_version
        == 1
    )


@pytest.mark.parametrize("method", METHODS)
def test_strict_result_models_reject_missing_fields_and_extra_fields(
    dispatcher: Dispatcher, method: str
) -> None:
    contract = Contract(method)
    result = next(
        example["result"] for example in contract.document["examples"] if "result" in example
    )
    model = dispatcher.lookup(method).result_model
    assert model is not None
    missing = dict(result)
    missing.pop(next(iter(missing)))
    with pytest.raises(ValidationError):
        model.model_validate(missing)
    with pytest.raises(ValidationError):
        model.model_validate(result | {"unknown": True})


def test_watchlist_cost_is_rejected_before_write(dispatcher: Dispatcher, db: Database) -> None:
    params = {"instrumentId": "us:ZZAR", "quantity": "0", "avgCost": "1"}
    assert not Contract("holdings.upsert").params.is_valid(params)
    response = call(dispatcher, "holdings.upsert", params)
    assert response["error"]["data"]["field"] == "avgCost"
    assert query(db, "SELECT count(*) FROM holding") == [(0,)]


def test_maximum_quantity_with_close_1000_matches_corrected_contract(
    dispatcher: Dispatcher, db: Database
) -> None:
    add_downstream(db, ("3.5",))
    with db.write() as tx:
        tx.execute(
            "INSERT INTO price_daily VALUES ('us:ZZAR', '2026-10-30', "
            "NULL, NULL, NULL, 1000, NULL, 1, 'demo', ?)",
            [NOW],
        )
    params = {"instrumentId": "us:ZZAR", "quantity": "99999999999999.9999"}
    contract = Contract("holdings.upsert")
    contract.params.validate(params)
    response = call(dispatcher, "holdings.upsert", params)
    contract.response(response)
    assert response["result"]["marketValue"] == "99999999999999999.9000"
    listed = call(dispatcher, "holdings.list", {})
    Contract("holdings.list").response(listed)
    assert listed["result"]["items"][0]["marketValue"] == "99999999999999999.9000"


@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity", True),
        ("quantity", 1.5),
        ("quantity", "1.00000"),
        ("quantity", "1"),
        ("avgCost", -1),
        ("avgCost", "NaN"),
        ("marketValue", float("inf")),
        ("marketValue", "-1.0000"),
        ("marketValue", "1.00000"),
        ("lastClose", float("nan")),
        ("lastClose", True),
        ("lastClose", -1),
        ("lastCloseDate", "2026-02-30"),
        ("lastCloseDate", "2026-11-2"),
        ("dayChangePct", float("inf")),
        ("thesisCount", True),
        ("pendingCount", -1),
        ("uncertainCount", 1.5),
        ("status", "invalid"),
    ],
)
def test_holding_result_rejects_bad_types_and_ranges(
    dispatcher: Dispatcher, field: str, value: object
) -> None:
    spec = dispatcher.lookup("holdings.upsert")
    example = Contract("holdings.upsert").document["examples"][0]["result"]
    with pytest.raises(ValidationError):
        spec.result_model.model_validate(example | {field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", True),
        ("version", 0),
        ("versionCount", 1.5),
        ("statement", " "),
        ("statement", "😀" * 501),
        ("killCondition", "😀" * 301),
        ("status", "invalid"),
        ("createdAt", "2026-11-02 00:35:00Z"),
        ("updatedAt", "2026-11-02T00:35:00+00:00"),
    ],
)
def test_thesis_result_rejects_bad_types_and_ranges(
    dispatcher: Dispatcher, field: str, value: object
) -> None:
    spec = dispatcher.lookup("thesis.create")
    example = Contract("thesis.create").document["examples"][0]["result"]
    with pytest.raises(ValidationError):
        spec.result_model.model_validate(example | {field: value})
