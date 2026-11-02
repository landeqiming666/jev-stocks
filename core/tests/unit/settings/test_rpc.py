import pytest
from pydantic import BaseModel

from sentinel.logging_setup import JsonFormatter
from sentinel.rpc import CancelToken, Dispatcher
from sentinel.rpc.dispatcher import RequestContext
from sentinel.secrets import SecretsService
from sentinel.settings import SettingsService, register
from sentinel.settings.models import EngineSnapshot
from sentinel.storage import Database

from .conftest import NOW, FakeProbe

METHODS = (
    "app.bootstrap",
    "settings.get",
    "settings.update",
    "settings.testConnection",
    "secrets.set",
    "secrets.clear",
    "secrets.status",
)


def test_register_installs_seven_methods(
    settings: SettingsService,
    secrets: SecretsService,
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    dispatcher = Dispatcher()
    args = (
        dispatcher,
        settings,
        secrets,
        db,
        "macos",
        EngineSnapshot("auto", "jev_direct", False),
        FakeProbe(),
    )
    register(*args)
    assert set(dispatcher.methods()) == set(METHODS)

    responses: list[dict] = []

    def call(method: str, params: dict) -> dict:
        result = dispatcher.dispatch(
            dispatcher.lookup(method), params, RequestContext("r-c04", method, CancelToken(), NOW)
        )
        responses.append(result)
        return result

    assert call("secrets.set", {"name": "jevKey", "value": " test-key-do-not-use "})["result"] == {
        "ok": True
    }
    assert call("secrets.status", {})["result"] == {"jevKey": True}
    assert call("settings.get", {})["result"]["engine"] == "auto"
    assert (
        call("settings.update", {"secContactEmail": "name@example.com"})["result"][
            "secContactEmail"
        ]
        == "name@example.com"
    )
    assert call("settings.testConnection", {})["result"]["ok"] is True
    assert call("settings.update", {"engine": "jevdb"})["result"]["engine"] == "jevdb"
    boot = call("app.bootstrap", {})["result"]
    assert boot["engine"] == dict(
        requested="jevdb", active=None, modelId="jev-1.14.0", jevdbAvailable=False
    )
    assert boot["offline"] is True
    monkeypatch.setenv("SENTINEL_OFFLINE", "true")
    assert call("app.bootstrap", {})["result"]["offline"] is False
    assert call("settings.testConnection", {})["result"]["ok"] is False
    assert (
        call("secrets.set", {"name": "jevKey", "value": " "})["error"]["data"]["field"] == "value"
    )
    assert call("secrets.clear", {"name": "jevKey"})["result"] == {"ok": True}
    assert call("app.bootstrap", {})["result"]["engine"]["active"] is None
    for method in METHODS:
        assert call(method, {"unknown": 1})["error"]["code"] == "INVALID_ARGUMENT"
    for patch in ({"dailyTokenBudget": True}, {"engine": "oops"}, {"modelId": "x"}):
        assert call("settings.update", patch)["error"]["code"] == "INVALID_ARGUMENT"
    assert call("secrets.getJevKey", {})["error"]["data"]["reason"] == "UNKNOWN_METHOD"
    with pytest.raises(ValueError):
        register(*args)
    assert set(dispatcher.methods()) == set(METHODS)
    with db.read() as reader:
        reader.execute("SELECT key, value_json FROM setting")
        assert "test-key-do-not-use" not in str(reader.fetchall())
    assert "test-key-do-not-use" not in str(responses)
    assert "test-key-do-not-use" not in "".join(JsonFormatter().format(r) for r in caplog.records)


def test_duplicate_preflight_and_result_internal(
    settings: SettingsService, secrets: SecretsService, db: Database
) -> None:
    dispatcher = Dispatcher()

    def invalid_result(params: BaseModel, ctx: RequestContext) -> dict[str, object]:
        return {"jevKey": "private-result"}

    from sentinel.settings.models import EmptyParams, SecretStatus

    dispatcher.register("secrets.status", invalid_result, EmptyParams, SecretStatus)
    with pytest.raises(ValueError):
        register(
            dispatcher,
            settings,
            secrets,
            db,
            "macos",
            EngineSnapshot("auto", None, False),
            FakeProbe(),
        )
    assert dispatcher.methods() == ("secrets.status",)
    response = dispatcher.dispatch(
        dispatcher.lookup("secrets.status"),
        {},
        RequestContext("r-c04", "secrets.status", CancelToken(), NOW),
    )
    assert response["error"]["code"] == "INTERNAL"
    assert "private-result" not in str(response)
