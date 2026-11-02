import json

import pytest
from pydantic import ValidationError

from sentinel.errors import InternalError, UserError
from sentinel.secrets import SecretsService
from sentinel.settings import SettingsService
from sentinel.settings.models import EngineSnapshot, SettingsPatch
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
    result = settings.update(SettingsPatch(dailyTokenBudget=3000000, engine="auto"))
    assert result.dailyTokenBudget == 3000000
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
    assert settings.update(SettingsPatch(dailyTokenBudget=10000)).dailyTokenBudget == 10000
    with pytest.raises(UserError):
        SettingsPatch(dailyTokenBudget=50000001)


def test_normalization_boundaries_and_noop(settings: SettingsService, db: Database) -> None:
    email = "x" * 114 + "@a.com"
    value = settings.update(
        SettingsPatch(
            secContactEmail="\x1c " + email + " \x1c",
            engine=" auto ",
            firstScanLookbackDays=30,
            dailyTokenBudget=50000000,
        )
    )
    assert value.secContactEmail == email and len(email) == 120
    with db.read() as reader:
        reader.execute("SELECT updated_at FROM setting")
        assert set(reader.fetchall()) == {(NOW,)}
    settings._clock = lambda: NOW.replace(year=2027)
    settings.update(SettingsPatch(secContactEmail=email))
    settings.update(SettingsPatch())
    with db.read() as reader:
        reader.execute("SELECT updated_at FROM setting")
        assert set(reader.fetchall()) == {(NOW,)}
    assert settings.update(SettingsPatch(secContactEmail=" \x1c\t")).secContactEmail is None


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
    assert settings.get().demoDataLoaded is True
    repo.write_patch({"demoDataLoaded": True}, NOW.replace(year=2027))
    with db.read() as reader:
        reader.execute("SELECT updated_at FROM setting")
        assert set(reader.fetchall()) == {(NOW,)}


def test_constructed_invalid_patch_never_writes(settings: SettingsService, db: Database) -> None:
    with pytest.raises(UserError):
        settings.update(SettingsPatch.model_construct(dailyTokenBudget=True))
    assert SettingsRepository(db).raw() == {}


def test_bootstrap_fields_match_contract(
    settings: SettingsService, secrets: SecretsService, db: Database
) -> None:
    secrets.set_jev_key("test-key-do-not-use")
    settings.update(SettingsPatch(secContactEmail="name@example.com"))
    result = settings.bootstrap(ENGINE, secrets, db, "macos", True).model_dump(mode="json")
    assert result == dict(
        protocolVersion="1.0",
        appVersion="0.1.0",
        dbSchemaVersion=1,
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
    settings.update(SettingsPatch(secContactEmail="name@example.com"))
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
    settings.update(SettingsPatch(secContactEmail="name@example.com"))
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
    settings.update(SettingsPatch(secContactEmail=email))
    probe = FakeProbe()
    with pytest.raises(UserError) as caught:
        settings.test_connection(probe, ENGINE)
    assert caught.value.to_wire()["data"]["missing"] == missing
    assert probe.calls == []
