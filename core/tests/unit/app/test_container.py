from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from sentinel.app.args import AppArgs
from sentinel.app.container import AppContainer, allowed_domains, build_container
from sentinel.app.probe import EngineProbe
from sentinel.errors import SentinelError
from sentinel.http import HttpClient
from sentinel.messages.settings import DOMAIN_RULES
from sentinel.scan.models import ScanConfiguration
from sentinel.secrets import MemorySecretStore
from sentinel.settings.models import EngineChoice

KEY = "sk-test-do-not-use"


def _config(engine: EngineChoice = "jev_direct") -> ScanConfiguration:
    return ScanConfiguration(
        engine=engine,
        model_id="jev-1.14.0",
        sec_contact_email="analyst@example.invalid",
        daily_token_budget=2_000_000,
        first_scan_lookback_days=7,
    )


def test_builds_services_and_applies_all_migrations(container: AppContainer) -> None:
    assert container.migrations_applied == 12
    assert container.db.schema_version == 12
    assert container.scan.db is container.db
    assert container.paper.db is container.db
    assert container.inbox is not None and container.demo is not None
    assert container.platform_name == "macos"


def test_missing_jev_key_still_boots_without_active_engine(container: AppContainer) -> None:
    assert container.settings.get().engine == "auto"
    assert container.secrets.status() == {"jevKey": False}
    assert container.engine.snapshot().active is None
    assert container.engine.health() == (None, "unconfigured")


def test_auto_falls_back_to_direct_and_records_change_once(
    container: AppContainer, store: MemorySecretStore
) -> None:
    store.set("typesafe_api_key", KEY)
    snapshot = container.engine.snapshot()
    assert snapshot.requested == "auto"
    assert snapshot.active == "jev_direct"
    assert snapshot.jevdb_available is False
    change = container.engine.take_change()
    assert change is not None and (change.from_engine, change.to_engine) == (
        "jevdb",
        "jev_direct",
    )
    assert container.engine.take_change() is None


def test_pipeline_uses_current_engine_and_budget(
    container: AppContainer, store: MemorySecretStore
) -> None:
    store.set("typesafe_api_key", KEY)
    pipeline = container.pipeline_for(_config())
    assert pipeline.engine.name == "jev_direct"
    assert pipeline.db is container.db
    assert pipeline.daily_budget == 2_000_000


def test_change_guard_rejects_while_scan_is_active(container: AppContainer) -> None:
    with container.db.write() as tx:
        tx.execute(
            "INSERT INTO scan_run (run_id, trigger, market, status, window_start, window_end,"
            " engine, model_id, question_set_version, created_at)"
            " VALUES ('run-1','manual','us','running','2026-10-26','2026-11-02','jev_direct',"
            "'jev-1.14.0','q1',?)",
            [datetime(2026, 11, 2, 8, 0, tzinfo=UTC)],
        )
    with pytest.raises(SentinelError) as caught, container.change_guard():
        pass
    assert caught.value.code == "CONFLICT"


def test_change_guard_closes_cached_engine(
    container: AppContainer, store: MemorySecretStore
) -> None:
    store.set("typesafe_api_key", KEY)
    assert container.engine.snapshot().active == "jev_direct"
    with container.change_guard():
        pass
    assert container.engine.current() is None


@dataclass
class _Response:
    status: int


class _RecordingHttp:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, **kwargs: object) -> _Response:
        self.calls.append({"url": url, **kwargs})
        return _Response(200)


def test_probe_sends_no_holdings_or_thesis(container: AppContainer) -> None:
    http = _RecordingHttp()
    probe = EngineProbe(container.engine, http=cast(HttpClient, http), offline=False)
    result = probe.check_sec("analyst@example.invalid")
    assert result.ok is True
    payload = json.dumps(http.calls, ensure_ascii=False)
    assert "holding" not in payload.lower()
    assert "thesis" not in payload.lower()
    assert "quantity" not in payload.lower()
    assert "analyst@example.invalid" in payload


def test_allowed_domains_replaces_model_host_only(tmp_path: Path) -> None:
    provider = allowed_domains("https://gateway.example.invalid/v1")
    rules = provider()
    assert rules[0]["domain"] == "gateway.example.invalid"
    assert rules[1:] == DOMAIN_RULES[1:]
    assert allowed_domains(None)()[0] == DOMAIN_RULES[0]


def test_build_container_reuses_secret_store_across_calls(args: AppArgs) -> None:
    store = MemorySecretStore()
    store.set("typesafe_api_key", KEY)
    first = build_container(args, secret_store=store)
    try:
        assert first.secrets.status()["jevKey"] is True
        second = build_container(args, secret_store=store)
        try:
            assert second.secrets.status()["jevKey"] is True
            assert second.engine.snapshot().active == "jev_direct"
        finally:
            second.close()
    finally:
        first.close()


def test_services_share_one_database_and_providers(container: AppContainer) -> None:
    assert container.scan.settings_provider == container.settings.get
    assert container.scan.holdings is container.portfolio
    assert container.scan.filings is container.filings
    assert container.risk.db is container.db
    assert container.paper.db is container.db
    assert container.demo is not None
