import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from sentinel.domain.contact import is_valid_sec_email
from sentinel.rpc import CancelToken, Dispatcher
from sentinel.rpc.dispatcher import RequestContext
from sentinel.secrets import SecretsService
from sentinel.settings import SettingsService, register
from sentinel.settings.models import EngineSnapshot, Settings, SettingsPatch, StoredSettings
from sentinel.storage import Database

from .conftest import NOW, FakeProbe
from .test_rpc import METHODS

CONTACT_CASES = [
    ("name@example.com", True),
    ("first.last+research@sub.example.co", True),
    ("a" * 64 + "@" + "b" * 51 + ".com", True),
    ("a" * 64 + "@" + "b" * 52 + ".com", False),
    ("a" * 65 + "@example.com", False),
    ("a@example..com", False),
    ("a..b@example.com", False),
    ("a@-example.com", False),
    ("a@example-.com", False),
    ("a@example.c", False),
    ("a@" + "b" * 64 + ".com", False),
    ("a\x00@example.com", False),
    ("a\x7f@example.com", False),
    ("\u96ea@example.com", False),
    ("a\x1cb@example.com", False),
    (" a@example.com ", False),
    ("a@example.com\n", False),
    ("", False),
    (None, False),
    (True, False),
]

CONTRACTS = Path(__file__).resolve().parents[4] / "contracts"
TYPES = json.loads((CONTRACTS / "types.schema.json").read_text())
REGISTRY = Registry().with_resource(
    "types.schema.json", Resource.from_contents(TYPES, default_specification=DRAFT202012)
)


class MachineContract:
    def __init__(self, method: str) -> None:
        self.document = json.loads((CONTRACTS / "methods" / (method + ".json")).read_text())
        self.params = Draft202012Validator(self.document["params"], registry=REGISTRY)
        self.result = Draft202012Validator(self.document["result"], registry=REGISTRY)
        self.error = Draft202012Validator(
            {"$ref": "types.schema.json#/$defs/RpcError"}, registry=REGISTRY
        )

    def response(self, response: dict) -> None:
        assert response["jsonrpc"] == "2.0" and response["id"] == "r-contract"
        if "error" in response:
            self.error.validate(response["error"])
        else:
            self.result.validate(response["result"])


@pytest.fixture
def dispatcher(settings: SettingsService, secrets: SecretsService, db: Database) -> Dispatcher:
    dispatcher = Dispatcher()
    register(
        dispatcher,
        settings,
        secrets,
        db,
        "macos",
        EngineSnapshot("auto", "jev_direct", False),
        FakeProbe(),
    )
    return dispatcher


def call(dispatcher: Dispatcher, method: str, params: dict) -> dict:
    return dispatcher.dispatch(
        dispatcher.lookup(method), params, RequestContext("r-contract", method, CancelToken(), NOW)
    )


@pytest.mark.parametrize("method", METHODS)
def test_canonical_examples_round_trip_registered_models(
    dispatcher: Dispatcher, method: str
) -> None:
    contract = MachineContract(method)
    spec = dispatcher.lookup(method)
    for example in contract.document["examples"]:
        if "result" in example:
            contract.params.validate(example["params"])
            spec.params_model.model_validate(example["params"], strict=True, extra="forbid")
            contract.result.validate(example["result"])
            parsed = spec.result_model.model_validate(
                example["result"], strict=True, extra="forbid"
            )
            assert parsed.model_dump(mode="json", by_alias=True) == example["result"]
        else:
            contract.error.validate(example["error"])


@pytest.mark.parametrize("value,canonical", CONTACT_CASES)
def test_raw_contact_machine_contract_matches_real_dispatcher(
    dispatcher: Dispatcher, value: object, canonical: bool
) -> None:
    contract = MachineContract("settings.update")
    params = {"secContactEmail": value}
    assert is_valid_sec_email(value) is canonical
    normalized = value.strip() or None if isinstance(value, str) else value
    valid = normalized is None or is_valid_sec_email(normalized)
    assert contract.params.is_valid(params) is valid
    result = call(dispatcher, "settings.update", params)
    contract.response(result)
    if valid:
        assert result["result"]["secContactEmail"] == normalized
    else:
        assert result["error"]["code"] == "INVALID_ARGUMENT"
        assert result["error"]["data"]["field"] == "secContactEmail"


@pytest.mark.parametrize("value,canonical", CONTACT_CASES)
def test_contact_policy_is_shared_by_stored_and_public_settings(
    settings: SettingsService, value: object, canonical: bool
) -> None:
    assert is_valid_sec_email(value) is canonical
    if canonical or value is None:
        assert StoredSettings.model_validate({"secContactEmail": value}).sec_contact_email == value
        public = settings.get().model_dump() | {"secContactEmail": value}
        assert Settings.model_validate(public).sec_contact_email == value
    else:
        with pytest.raises((ValidationError, TypeError, ValueError)):
            StoredSettings.model_validate({"secContactEmail": value})
        public = settings.get().model_dump() | {"secContactEmail": value}
        with pytest.raises((ValidationError, TypeError, ValueError)):
            Settings.model_validate(public)


@pytest.mark.parametrize("method", METHODS)
def test_seven_actual_results_and_closed_inputs_match_machine_contract(
    dispatcher: Dispatcher,
    secrets: SecretsService,
    settings: SettingsService,
    method: str,
) -> None:
    secrets.set_jev_key("test-key-do-not-use")
    settings.update(SettingsPatch(sec_contact_email="name@example.com"))
    params = {
        "secrets.set": {"name": "jevKey", "value": " test-key-do-not-use "},
        "secrets.clear": {"name": "jevKey"},
    }.get(method, {})
    contract = MachineContract(method)
    contract.params.validate(params)
    result = call(dispatcher, method, params)
    assert "result" in result
    contract.response(result)
    unknown = params | {"unknown": "private-input"}
    with pytest.raises(ValidationError):
        contract.params.validate(unknown)
    rejected = call(dispatcher, method, unknown)
    contract.response(rejected)
    assert rejected["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize(
    "field", ["sec_contact_email", "daily_token_budget", "first_scan_lookback_days"]
)
def test_contract_schema_rejects_python_field_names(field: str) -> None:
    contract = MachineContract("settings.update")
    params = {
        field: "name@example.com" if "email" in field else 7 if "lookback" in field else 10000
    }
    assert not contract.params.is_valid(params)
    # Internal Pydantic models also accept snake_case; RPC wire names remain camelCase.
    if field == "first_scan_lookback_days":
        params[field] = 7
    assert SettingsPatch.model_validate(params, strict=True, extra="forbid")
