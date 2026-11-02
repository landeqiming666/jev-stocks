from collections.abc import Iterator
from pathlib import Path

import pytest

from sentinel.clock import parse_iso
from sentinel.secrets import MemorySecretStore, SecretsService
from sentinel.settings import SettingsService
from sentinel.settings.models import ProbeResult
from sentinel.settings.repository import SettingsRepository
from sentinel.storage import Database

NOW = parse_iso("2026-11-02T00:35:00Z")


class FakeProbe:
    def __init__(self, failed: str = "JEVDB", raises: bool = False) -> None:
        self.calls: list[str] = []
        self.failed, self.raises = failed, raises

    def check(self, name: str, latency: int) -> ProbeResult:
        self.calls.append(name)
        if name == self.failed and self.raises:
            raise RuntimeError("private-payload test-key-do-not-use")
        return ProbeResult(ok=name != self.failed, latencyMs=latency, message="private-payload")

    def check_jev(self, model_id: str) -> ProbeResult:
        assert model_id == "jev-1.14.0"
        return self.check("Jev", 412)

    def check_sec(self, email: str) -> ProbeResult:
        assert email == "name@example.com"
        return self.check("SEC", 236)

    def check_jevdb(self) -> ProbeResult:
        return self.check("JEVDB", 0)


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Database]:
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    monkeypatch.setenv("SENTINEL_CLOCK", "2026-11-02T00:35:00Z")
    database = Database(tmp_path / "sentinel.duckdb")
    database.open()
    database.migrate()
    yield database
    database.close()


@pytest.fixture
def secrets() -> SecretsService:
    return SecretsService(MemorySecretStore(), lambda: NOW)


@pytest.fixture
def settings(db: Database, secrets: SecretsService) -> SettingsService:
    service = SettingsService(SettingsRepository(db), lambda: NOW)
    service.bind_secrets(secrets)
    return service
