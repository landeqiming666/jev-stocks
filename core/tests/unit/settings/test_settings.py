import json

import pytest
from pydantic import ValidationError

from sentinel.errors import InternalError, UserError
from sentinel.messages.settings import MESSAGES
from sentinel.secrets import SecretsService
from sentinel.settings import SettingsService
from sentinel.settings.models import EngineSnapshot, SettingsPatch, StoredSettings
from sentinel.settings.repository import SettingsRepository
from sentinel.storage import Database

from .conftest import NOW, FakeProbe

ENGINE = EngineSnapshot("auto", "jev_direct", False)


def test_defaults_match_docs_04(settings: SettingsService, db: Database) -> None:
    result = settings.get().model_dump(mode="json")
    assert result | {"allowedDomains": []} == dict(
        engine="auto",
        modelId="jev-1.14.0",
        secContactEmail=None,
        dailyTokenBudget=2000000,
        firstScanLookbackDays=7,
        demoDataLoaded=False,
        language="zh-CN",
        allowedDomains=[],
    )
    assert [d["domain"] for d in result["allowedDomains"]] == [
        "api.typesafe.ai",
        "www.sec.gov",
        "data.sec.gov",
        "web.ifzq.gtimg.cn",
        "api.nasdaq.com",
    ]
    assert SettingsRepository(db).raw() == {}


def test_update_writes_only_changed_keys(settings: SettingsService, db: Database) -> None:
    result = settings.update(SettingsPatch(daily_token_budget=3000000, engine="auto"))
    assert result.daily_token_budget == 3000000
    assert SettingsRepository(db).raw() == {"dailyTokenBudget": 3000000}
    with db.read() as reader:
        reader.execute("SELECT updated_at FROM setting")
        assert reader.fetchone() == (NOW,)


@pytest.mark.parametrize(
    "patch,field",
    [
        ({"secContactEmail": "not-an-email"}, "secContactEmail"),
        ({"modelId": "x"}, "modelId"),
        ({"dailyTokenBudget": 50000001}, "dailyTokenBudget"),
        ({"dailyTokenBudget": True}, "dailyTokenBudget"),
        ({"firstScanLookbackDays": False}, "firstScanLookbackDays"),
        ({"dailyTokenBudget": "10000"}, "dailyTokenBudget"),
        ({"engine": None}, "engine"),
        ({"firstScanLookbackDays": 0}, "firstScanLookbackDays"),
        ({"dailyTokenBudget": None}, "dailyTokenBudget"),
        ({"secContactEmail": "x" * 115 + "@a.com"}, "secContactEmail"),
    ],
)
def test_invalid_email_has_field(patch: dict, field: str) -> None:
    with pytest.raises(UserError) as caught:
        SettingsPatch.model_validate(patch)
    assert caught.value.code == "INVALID_ARGUMENT" and caught.value.field == field


def test_unknown_patch_field_is_rejected(settings: SettingsService, db: Database) -> None:
    with pytest.raises(UserError):
        settings.update(SettingsPatch.model_validate({"modelId": "x"}))
    assert SettingsRepository(db).raw() == {}


def test_budget_out_of_range_is_rejected(settings: SettingsService) -> None:
    assert settings.update(SettingsPatch(daily_token_budget=10000)).daily_token_budget == 10000
    with pytest.raises(UserError):
        SettingsPatch(daily_token_budget=50000001)


def test_normalization_boundaries_and_noop(settings: SettingsService, db: Database) -> None:
    email = "x" * 64 + "@" + "a" * 48 + ".abcdef"
    value = settings.update(
        SettingsPatch(
            sec_contact_email="\x1c " + email + " \x1c",
            engine="auto",
            first_scan_lookback_days=30,
            daily_token_budget=50000000,
        )
    )
    assert value.sec_contact_email == email and len(email) == 120
    with db.read() as reader:
        reader.execute("SELECT updated_at FROM setting")
        assert set(reader.fetchall()) == {(NOW,)}
    settings._clock = lambda: NOW.replace(year=2027)
    settings.update(SettingsPatch(sec_contact_email=email))
    settings.update(SettingsPatch())
    with db.read() as reader:
        reader.execute("SELECT updated_at FROM setting")
        assert set(reader.fetchall()) == {(NOW,)}
    assert settings.update(SettingsPatch(sec_contact_email=" \x1c\t")).sec_contact_email is None


@pytest.mark.parametrize("value", ["{", "NaN", "true", '"wrong"'])
def test_corrupt_json_never_falls_back(settings: SettingsService, db: Database, value: str) -> None:
    with db.write() as tx:
        tx.execute("INSERT INTO setting VALUES (?, ?, ?)", ["dailyTokenBudget", value, NOW])
    with pytest.raises(InternalError):
        settings.update(SettingsPatch(engine="jevdb"))
    with db.read() as reader:
        reader.execute("SELECT key, value_json FROM setting")
        assert reader.fetchall() == [("dailyTokenBudget", value)]


def test_atomic_rollback(db: Database) -> None:
    repo = SettingsRepository(db)
    with db.write() as tx:
        tx.execute(
            "CREATE OR REPLACE TABLE setting (key VARCHAR PRIMARY KEY "
            "CHECK (key <> 'firstScanLookbackDays'), value_json VARCHAR NOT NULL, "
            "updated_at TIMESTAMP NOT NULL)"
        )
    with pytest.raises(InternalError):
        repo.write_patch({"engine": "jevdb", "firstScanLookbackDays": 10}, NOW)
    assert repo.raw() == {}


def test_repository_noop_keeps_timestamp_and_readonly_keys(
    settings: SettingsService, db: Database
) -> None:
    repo = SettingsRepository(db)
    repo.write_patch(
        {
            "demoDataLoaded": True,
            "lastTickerRefreshAt": "2026-11-02T00:35:00Z",
            "lastPriceRefreshAt": None,
            "modelId": "jev-1.14.0",
        },
        NOW,
    )
    assert settings.get().demo_data_loaded is True
    repo.write_patch({"demoDataLoaded": True}, NOW.replace(year=2027))
    with db.read() as reader:
        reader.execute("SELECT updated_at FROM setting")
        assert set(reader.fetchall()) == {(NOW,)}


def test_constructed_invalid_patch_never_writes(settings: SettingsService, db: Database) -> None:
    with pytest.raises(UserError):
        settings.update(SettingsPatch.model_construct(daily_token_budget=True))
    assert SettingsRepository(db).raw() == {}


def test_bootstrap_fields_match_contract(
    settings: SettingsService, secrets: SecretsService, db: Database
) -> None:
    secrets.set_jev_key("test-key-do-not-use")
    settings.update(SettingsPatch(sec_contact_email="name@example.com"))
    result = settings.bootstrap(ENGINE, secrets, db, "macos", True).model_dump(mode="json")
    assert result == dict(
        protocolVersion="1.0",
        appVersion="0.1.0",
        dbSchemaVersion=db.schema_version,
        platform="macos",
        engine=dict(
            requested="auto", active="jev_direct", modelId="jev-1.14.0", jevdbAvailable=False
        ),
        markets=["us"],
        configured=dict(jevKey=True, secEmail=True),
        demoDataLoaded=False,
        offline=True,
        now="2026-11-02T00:35:00Z",
    )
    assert "test-key-do-not-use" not in json.dumps(result)


def test_bootstrap_unconfigured_has_no_active_engine(
    settings: SettingsService, secrets: SecretsService, db: Database
) -> None:
    assert settings.bootstrap(ENGINE, secrets, db, "windows", False).engine.active is None
    with pytest.raises(ValidationError):
        settings.bootstrap(ENGINE, secrets, db, "linux", False)


@pytest.mark.parametrize(
    "failed,raises", [("JEVDB", False), ("Jev", False), ("SEC", True), ("JEVDB", True)]
)
def test_connection_ok_when_jevdb_missing(
    settings: SettingsService, secrets: SecretsService, failed: str, raises: bool
) -> None:
    secrets.set_jev_key("test-key-do-not-use")
    settings.update(SettingsPatch(sec_contact_email="name@example.com"))
    probe = FakeProbe(failed, raises)
    result = settings.test_connection(probe, ENGINE)
    assert result.ok == (failed == "JEVDB")
    assert probe.calls == ["Jev", "SEC", "JEVDB"]
    assert all(check.ok == (check.name != failed) for check in result.checks)
    assert "private-payload" not in result.model_dump_json()
    assert "test-key-do-not-use" not in result.model_dump_json()


def test_connection_false_when_jev_fails(
    settings: SettingsService, secrets: SecretsService
) -> None:
    secrets.set_jev_key("test-key-do-not-use")
    settings.update(SettingsPatch(sec_contact_email="name@example.com"))
    assert not settings.test_connection(FakeProbe("Jev"), ENGINE).ok


@pytest.mark.parametrize(
    "key,email,missing",
    [
        (False, None, ["jevKey", "secEmail"]),
        (True, None, ["secEmail"]),
        (False, "name@example.com", ["jevKey"]),
    ],
)
def test_connection_missing_config(
    settings: SettingsService,
    secrets: SecretsService,
    key: bool,
    email: str | None,
    missing: list[str],
) -> None:
    if key:
        secrets.set_jev_key("test-key-do-not-use")
    settings.update(SettingsPatch(sec_contact_email=email))
    probe = FakeProbe()
    with pytest.raises(UserError) as caught:
        settings.test_connection(probe, ENGINE)
    assert caught.value.to_wire()["data"]["missing"] == missing
    assert probe.calls == []


WHITESPACE = tuple(
    map(
        chr,
        [
            *range(9, 14),
            *range(28, 33),
            0x85,
            0xA0,
            0x1680,
            *range(0x2000, 0x200B),
            0x2028,
            0x2029,
            0x202F,
            0x205F,
            0x3000,
        ],
    )
)


@pytest.mark.parametrize("whitespace", WHITESPACE, ids=lambda value: f"U+{ord(value):04X}")
def test_all_python_whitespace_normalizes_only_email(whitespace: str) -> None:
    assert len(WHITESPACE) == 29 and whitespace.isspace()
    assert (
        SettingsPatch(
            sec_contact_email=whitespace + "name@example.com" + whitespace
        ).sec_contact_email
        == "name@example.com"
    )
    assert SettingsPatch.model_validate({"secContactEmail": whitespace}).sec_contact_email is None
    for email in ("a" + whitespace + "b@example.com", "a@exa" + whitespace + "mple.com"):
        with pytest.raises(UserError) as caught:
            SettingsPatch.model_validate({"secContactEmail": email})
        assert caught.value.field == "secContactEmail"
        assert caught.value.message_key == "settings.email_invalid"
        assert email not in MESSAGES[caught.value.message_key].format()
        with pytest.raises(ValidationError):
            StoredSettings(sec_contact_email=email)


def test_email_enforces_ascii_and_local_part_limit_after_normalization() -> None:
    email = "x" * 64 + "@" + "a" * 48 + ".abcdef"
    assert len(email) == 120
    assert SettingsPatch(sec_contact_email="\x1c" + email + "\x1f").sec_contact_email == email
    for invalid in ("x" * 65 + "@a.com", "😀@a.com", "x@例子.测试"):
        with pytest.raises(UserError) as caught:
            SettingsPatch(sec_contact_email=invalid)
        assert caught.value.message_key == "settings.email_invalid"


@pytest.mark.parametrize("engine", [" auto ", "\x1cauto\x1c", "AUTO", "jevdb "])
def test_engine_enum_is_never_trimmed(engine: str) -> None:
    with pytest.raises(UserError) as caught:
        SettingsPatch(engine=engine)
    assert caught.value.field == "engine"


@pytest.mark.parametrize("available", [False, True])
def test_requested_jevdb_never_constructs_an_active_engine(
    settings: SettingsService, secrets: SecretsService, db: Database, available: bool
) -> None:
    secrets.set_jev_key("test-key-do-not-use")
    settings.update(SettingsPatch(engine="jevdb", sec_contact_email="name@example.com"))
    actual = EngineSnapshot("auto", "jev_direct", available)
    snapshot = settings.engine_snapshot(actual)
    assert snapshot == EngineSnapshot("jevdb", "jev_direct", available)
    bootstrap = settings.bootstrap(actual, secrets, db, "macos", False)
    assert bootstrap.engine.requested == "jevdb" and bootstrap.engine.active == "jev_direct"
    assert bootstrap.engine.jevdb_available is available
    assert settings.test_connection(FakeProbe(), actual).engine == "jev_direct"
    assert settings.engine_snapshot(EngineSnapshot("auto", None, available)).active is None


def test_corrupt_setting_selects_domain_message(settings: SettingsService, db: Database) -> None:
    for raw in ("{", "true"):
        with db.write() as tx:
            tx.execute(
                "INSERT INTO setting VALUES (?, ?, ?) ON CONFLICT (key) "
                "DO UPDATE SET value_json=excluded.value_json",
                ["dailyTokenBudget", raw, NOW],
            )
        with pytest.raises(InternalError) as caught:
            settings.get()
        assert caught.value.message_key == "settings.data_corrupt"
        assert MESSAGES[caught.value.message_key].format()


def test_snake_case_fields_alias_input_and_wire_output(settings: SettingsService) -> None:
    import re

    from sentinel.settings import models

    for value in vars(models).values():
        if isinstance(value, type) and issubclass(value, models.WireModel):
            assert all(re.fullmatch(r"[a-z][a-z0-9_]*", name) for name in value.model_fields)
    patch = SettingsPatch(sec_contact_email="name@example.com", daily_token_budget=3000000)
    assert patch.model_dump(exclude_unset=True) == {
        "secContactEmail": "name@example.com",
        "dailyTokenBudget": 3000000,
    }
    assert SettingsPatch.model_validate(patch.model_dump()).daily_token_budget == 3000000
    assert settings.update(patch).sec_contact_email == "name@example.com"
