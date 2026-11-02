from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from pydantic import ValidationError

from sentinel import __version__
from sentinel.clock import to_iso
from sentinel.errors import InternalError, UserError
from sentinel.logging_setup import get_logger, log_event
from sentinel.messages.settings import DOMAIN_RULES, MESSAGES
from sentinel.secrets import SecretsService
from sentinel.storage import Database

from .models import (
    MODEL_ID,
    Bootstrap,
    ConnectionCheck,
    ConnectionTestResult,
    DomainRule,
    EngineSnapshot,
    ProbeResult,
    Settings,
    SettingsPatch,
    StoredSettings,
)
from .repository import SettingsRepository

DEFAULT_ENGINE = "auto"
DEFAULT_BUDGET = 2_000_000
DEFAULT_LOOKBACK = 7


class ConnectionProbe(Protocol):
    def check_jev(self, model_id: str) -> ProbeResult: ...
    def check_sec(self, email: str) -> ProbeResult: ...
    def check_jevdb(self) -> ProbeResult: ...


class SettingsService:
    def __init__(self, repo: SettingsRepository, clock: Callable[[], datetime]) -> None:
        self._repo, self._clock = repo, clock
        self._secrets: SecretsService | None = None
        self._lock = threading.RLock()

    def bind_secrets(self, secrets: SecretsService) -> None:
        self._secrets = secrets

    def get(self) -> Settings:
        with self._lock:
            try:
                stored = StoredSettings.model_validate(self._repo.raw())
            except ValidationError as exc:
                field = str(exc.errors()[0]["loc"][0])
                log_event(
                    get_logger(__name__),
                    logging.ERROR,
                    event="settings.data_corrupt",
                    error_code="INTERNAL",
                )
                raise InternalError(detail=f"setting:{field}") from None
            values = stored.model_dump(exclude={"lastTickerRefreshAt", "lastPriceRefreshAt"})
            return Settings.model_validate(
                values
                | {
                    "language": "zh-CN",
                    "allowedDomains": [DomainRule.model_validate(rule) for rule in DOMAIN_RULES],
                }
            )

    def update(self, patch: SettingsPatch) -> Settings:
        with self._lock:
            # 重新验证绕过构造器的 model_construct/model_copy，验证完成后才允许写入。
            patch = SettingsPatch.model_validate(patch)
            current = self.get().model_dump()
            changed = {
                key: value
                for key, value in patch.model_dump(exclude_unset=True).items()
                if current[key] != value
            }
            if changed:
                self._repo.write_patch(changed, self._clock())
            return self.get()

    def engine_snapshot(self, engine: EngineSnapshot) -> EngineSnapshot:
        requested = self.get().engine
        active = engine.active
        if requested != engine.requested:
            active = (
                "jev_direct"
                if requested == "jev_direct"
                else "jevdb"
                if engine.jevdb_available
                else "jev_direct"
                if requested == "auto"
                else None
            )
        return EngineSnapshot(requested, active, engine.jevdb_available)

    def bootstrap(
        self,
        engine: EngineSnapshot,
        secrets: SecretsService,
        db: Database,
        platform_name: str,
        offline: bool,
    ) -> Bootstrap:
        with self._lock:
            settings = self.get()
            snapshot = self.engine_snapshot(engine)
            configured = secrets.status() | {"secEmail": settings.secContactEmail is not None}
            return Bootstrap.model_validate(
                dict(
                    protocolVersion="1.0",
                    appVersion=__version__,
                    dbSchemaVersion=db.schema_version,
                    platform=platform_name,
                    engine=dict(
                        requested=snapshot.requested,
                        active=snapshot.active if configured["jevKey"] else None,
                        modelId=MODEL_ID,
                        jevdbAvailable=snapshot.jevdb_available,
                    ),
                    markets=["us"],
                    configured=configured,
                    demoDataLoaded=settings.demoDataLoaded,
                    offline=offline,
                    now=to_iso(self._clock()),
                )
            )

    def test_connection(
        self, probe: ConnectionProbe, engine: EngineSnapshot
    ) -> ConnectionTestResult:
        settings = self.get()
        has_key = self._secrets is not None and self._secrets.status()["jevKey"]
        missing = (["jevKey"] if not has_key else []) + (
            ["secEmail"] if settings.secContactEmail is None else []
        )
        if missing:
            raise UserError("CONFIG_REQUIRED", params={"missing": missing})
        assert settings.secContactEmail is not None
        email = settings.secContactEmail
        snapshot = self.engine_snapshot(engine)
        checks: list[ConnectionCheck] = []
        steps: tuple[tuple[str, Callable[[], ProbeResult], str], ...] = (
            ("Jev", lambda: probe.check_jev(MODEL_ID), "jev"),
            ("SEC", lambda: probe.check_sec(email), "sec"),
            ("JEVDB", probe.check_jevdb, "jevdb"),
        )
        for name, call, message_key in steps:
            try:
                result = ProbeResult.model_validate(call(), strict=True)
            except Exception:
                log_event(
                    get_logger(__name__),
                    logging.WARNING,
                    event="settings.probe_failed",
                    error_code="SOURCE_UNAVAILABLE",
                    check=name,
                )
                result = ProbeResult(ok=False)
            suffix = "ok" if result.ok else "fallback" if name == "JEVDB" else "failed"
            message = MESSAGES[f"settings.{message_key}_{suffix}"].format(modelId=MODEL_ID)
            checks.append(
                ConnectionCheck.model_validate(
                    dict(name=name, ok=result.ok, latencyMs=result.latencyMs, message=message)
                )
            )
        return ConnectionTestResult(
            ok=checks[0].ok and checks[1].ok and snapshot.active is not None,
            engine=snapshot.active,
            modelId=MODEL_ID,
            checks=checks,
        )
