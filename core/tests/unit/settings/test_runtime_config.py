from sentinel.errors import UserError
from sentinel.messages.settings import DOMAIN_RULES
from sentinel.rpc import CancelToken, Dispatcher
from sentinel.rpc.dispatcher import RequestContext
from sentinel.settings import SettingsService, register
from sentinel.settings.models import EngineSnapshot
from sentinel.settings.repository import SettingsRepository

from .conftest import NOW, FakeProbe


def call(dispatcher, method, params=None):
    return dispatcher.dispatch(
        dispatcher.lookup(method),
        params or {},
        RequestContext("r-runtime", method, CancelToken(), NOW),
    )


def test_bootstrap_resolves_current_engine_after_configuration_changes(settings, secrets, db):
    current = [EngineSnapshot("auto", "jev_direct", False)]
    dispatcher = Dispatcher()
    register(dispatcher, settings, secrets, db, "macos", lambda: current[0], FakeProbe())
    call(dispatcher, "secrets.set", {"name": "jevKey", "value": "synthetic-runtime-key"})
    assert call(dispatcher, "app.bootstrap")["result"]["engine"]["active"] == "jev_direct"
    call(dispatcher, "settings.update", {"engine": "jevdb"})
    current[0] = EngineSnapshot("jevdb", "jevdb", True)
    assert call(dispatcher, "app.bootstrap")["result"]["engine"] == {
        "requested": "jevdb",
        "active": "jevdb",
        "modelId": "jev-1.14.0",
        "jevdbAvailable": True,
    }
    call(dispatcher, "secrets.clear", {"name": "jevKey"})
    assert call(dispatcher, "app.bootstrap")["result"]["engine"]["active"] is None


def test_configuration_guard_blocks_settings_and_secrets_without_writes(settings, secrets, db):
    dispatcher = Dispatcher()
    secrets.set_jev_key("synthetic-original-key")

    def guard():
        raise UserError("CONFLICT", reason="SCAN_RUNNING")

    register(
        dispatcher,
        settings,
        secrets,
        db,
        "macos",
        EngineSnapshot("auto", "jev_direct", False),
        FakeProbe(),
        before_change=guard,
    )
    for method, params in [
        ("settings.update", {"dailyTokenBudget": 10000}),
        ("secrets.set", {"name": "jevKey", "value": "synthetic-replacement-key"}),
        ("secrets.clear", {"name": "jevKey"}),
    ]:
        response = call(dispatcher, method, params)
        assert response["error"]["code"] == "CONFLICT"
        assert response["error"]["data"]["reason"] == "SCAN_RUNNING"
    assert settings.get().daily_token_budget == 2_000_000
    assert secrets.get_jev_key() == "synthetic-original-key"
    assert call(dispatcher, "settings.get")["result"]["dailyTokenBudget"] == 2_000_000


def test_connection_test_uses_live_snapshot(settings, secrets, db):
    dispatcher = Dispatcher()
    current = [EngineSnapshot("auto", None, False)]
    register(dispatcher, settings, secrets, db, "macos", lambda: current[0], FakeProbe())
    call(dispatcher, "secrets.set", {"name": "jevKey", "value": "synthetic-runtime-key"})
    call(dispatcher, "settings.update", {"secContactEmail": "name@example.com"})
    assert call(dispatcher, "settings.testConnection")["result"]["ok"] is False
    current[0] = EngineSnapshot("auto", "jev_direct", False)
    assert call(dispatcher, "settings.testConnection")["result"]["ok"] is True


def test_allowed_domains_can_disclose_explicit_gateway_without_mutating_defaults(db):
    rules = [dict(rule) for rule in DOMAIN_RULES]
    rules[0]["domain"] = "gateway.unit.invalid"
    settings = SettingsService(SettingsRepository(db), lambda: NOW, allowed_domains=lambda: rules)
    first = settings.get()
    assert first.allowed_domains[0].domain == "gateway.unit.invalid"
    assert len(first.allowed_domains) == 5
    assert DOMAIN_RULES[0]["domain"] == "api.typesafe.ai"
    rules[0]["domain"] = "replacement.unit.invalid"
    assert settings.get().allowed_domains[0].domain == "replacement.unit.invalid"
    assert first.allowed_domains[0].domain == "gateway.unit.invalid"
