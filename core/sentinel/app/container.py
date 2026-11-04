"""唯一的组合根：按固定顺序构造数据库、设置、数据源、引擎与业务服务。"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from sentinel import clock, platform
from sentinel.demo import DemoService
from sentinel.http import HttpClient
from sentinel.logging_setup import get_logger, log_event
from sentinel.markets.instruments import (
    InstrumentRepository,
    InstrumentService,
    SecTickerSource,
)
from sentinel.markets.prices import PriceService
from sentinel.markets.prices.calendar import TradingCalendar
from sentinel.markets.prices.nasdaq import NasdaqPriceSource
from sentinel.markets.prices.tencent import TencentPriceSource
from sentinel.markets.sec import SecFilingsClient, SecFilingsRepository, SecFilingsService
from sentinel.messages.settings import DOMAIN_RULES
from sentinel.portfolio import PortfolioService
from sentinel.quant import RiskService
from sentinel.scan import ScanService
from sentinel.scan.models import ScanConfiguration
from sentinel.scan.pending import InboxService
from sentinel.secrets import (
    KeyringSecretStore,
    MemorySecretStore,
    SecretsService,
    SecretStore,
)
from sentinel.semantic.pipeline import DecisionPipeline
from sentinel.settings import SettingsService
from sentinel.settings.models import MODEL_ID
from sentinel.settings.repository import SettingsRepository
from sentinel.storage import Database
from sentinel.trading import PaperService
from sentinel.trading.rules import MarketRules

from .args import AppArgs
from .engines import ENV_ENDPOINT, EngineRuntime
from .errors import StartupError
from .probe import EngineProbe
from .status import RuntimeStatus

_LOG = get_logger(__name__)


def allowed_domains(endpoint: str | None) -> Callable[[], Sequence[Mapping[str, str]]]:
    """把实际模型网关域名显示给用户；默认五项保持不变。"""

    def provider() -> Sequence[Mapping[str, str]]:
        rules: list[dict[str, str]] = [dict(rule) for rule in DOMAIN_RULES]
        if endpoint:
            host = urlsplit(endpoint).hostname
            if host:
                rules[0] = {**rules[0], "domain": host}
        return rules

    return provider


@dataclass
class AppContainer:
    args: AppArgs
    db: Database
    settings: SettingsService
    secrets: SecretsService
    http: HttpClient
    instruments_repo: InstrumentRepository
    instruments: InstrumentService
    filings: SecFilingsService
    prices: PriceService
    engine: EngineRuntime
    probe: EngineProbe
    portfolio: PortfolioService
    inbox: InboxService
    paper: PaperService
    risk: RiskService
    scan: ScanService
    demo: DemoService
    migrations_applied: int = 0
    offline: bool = False
    platform_name: str = "macos"
    _notifier: Callable[[str, dict[str, object]], None] | None = field(default=None, repr=False)

    # -- 通知 -------------------------------------------------------------
    def attach_notifier(self, notify: Callable[[str, dict[str, object]], None]) -> None:
        self._notifier = notify

    def notify(self, name: str, payload: dict[str, object]) -> None:
        if self._notifier is not None:
            self._notifier(name, payload)

    # -- 扫描流水线 -------------------------------------------------------
    def pipeline_for(self, config: ScanConfiguration) -> DecisionPipeline:
        return _pipeline(self.db, self.engine, config)

    def change_guard(self) -> AbstractContextManager[None]:
        return self._change_guard()

    @contextmanager
    def _change_guard(self) -> Iterator[None]:
        try:
            with self.scan.configuration_guard():
                yield
        finally:
            # 设置或密钥一旦可能改变，下一次调用必须重建引擎并读取当前配置。
            self.engine.invalidate()

    def pending_count(self) -> int:
        return self.inbox.list_inbox().summary.pending_count

    def close(self) -> None:
        self.engine.close()
        self.http.close()
        self.db.close()


def _secret_store() -> SecretStore:
    try:
        return KeyringSecretStore()
    except Exception:
        # 钥匙串不可用时仍允许启动；密钥不会持久化，设置页会显示未配置。
        log_event(
            _LOG,
            logging.WARNING,
            event="secrets.keyring_fallback",
            error_code="INTERNAL",
            reason="MEMORY_STORE",
        )
        return MemorySecretStore()


def build_container(args: AppArgs, *, secret_store: SecretStore | None = None) -> AppContainer:
    data_dir = args.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    platform.harden_permissions(data_dir)

    db = Database(data_dir / "sentinel.duckdb")
    db.open()
    try:
        report = db.migrate()
    except Exception as exc:
        db.close()
        raise StartupError(StartupError.MIGRATION_FAILED, type(exc).__name__) from None

    settings = SettingsService(
        SettingsRepository(db),
        clock.now,
        allowed_domains=allowed_domains(os.environ.get(ENV_ENDPOINT)),
    )
    secrets = SecretsService(secret_store or _secret_store(), clock.now)
    http = HttpClient(cache_dir=data_dir / "cache")
    email_provider = lambda: settings.get().sec_contact_email  # noqa: E731

    instruments_repo = InstrumentRepository(db)
    instruments = InstrumentService(
        instruments_repo, SecTickerSource(http, email_provider=email_provider), clock.now
    )
    filings = SecFilingsService(
        SecFilingsClient(http, email_provider=email_provider),
        SecFilingsRepository(db),
        clock.now,
    )
    prices = PriceService(
        db,
        NasdaqPriceSource(http),
        TencentPriceSource(http),
        args.resource_dir / "calendars" / "us.json",
        clock.now,
    )

    engine = EngineRuntime(
        choice=lambda: settings.get().engine,
        secret=secrets.get_jev_key,
        env=os.environ,
    )
    probe = EngineProbe(engine, http=http, offline=os.environ.get("SENTINEL_OFFLINE") == "1")

    portfolio = PortfolioService(db)
    paper = PaperService(db, MarketRules(), clock=clock.now)
    risk = RiskService(db, calendar=TradingCalendar(args.resource_dir / "calendars" / "us.json"))
    offline = os.environ.get("SENTINEL_OFFLINE") == "1"
    inbox = InboxService(db, status_provider=RuntimeStatus(engine=engine, offline=offline))
    scan = ScanService(
        db,
        settings_provider=settings.get,
        key_provider=lambda: secrets.status()["jevKey"],
        holdings_provider=portfolio,
        instrument_provider=instruments_repo.get,
        filings=filings,
        pipeline_resolver=lambda config: _pipeline(db, engine, config),
        pending_count_provider=lambda: inbox.list_inbox().summary.pending_count,
    )
    demo = DemoService(db, args.resource_dir / "demo", clock.now)

    container = AppContainer(
        args=args,
        db=db,
        settings=settings,
        secrets=secrets,
        http=http,
        instruments_repo=instruments_repo,
        instruments=instruments,
        filings=filings,
        prices=prices,
        engine=engine,
        probe=probe,
        portfolio=portfolio,
        inbox=inbox,
        paper=paper,
        risk=risk,
        scan=scan,
        demo=demo,
        migrations_applied=len(report.applied),
        offline=offline,
        platform_name=platform.name(),
    )
    return container


def _pipeline(db: Database, engine: EngineRuntime, config: ScanConfiguration) -> DecisionPipeline:
    return DecisionPipeline(
        db,
        engine.engine_for(config.engine),
        model_id=config.model_id,
        daily_budget=config.daily_token_budget,
    )


__all__ = ["AppContainer", "MODEL_ID", "allowed_domains", "build_container"]
