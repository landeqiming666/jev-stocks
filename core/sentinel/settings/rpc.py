from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import cast

from pydantic import BaseModel

from sentinel.rpc import Dispatcher
from sentinel.rpc.dispatcher import RequestContext
from sentinel.secrets import SecretsService
from sentinel.storage import Database

from .models import (
    Bootstrap,
    ConnectionTestResult,
    EmptyParams,
    EngineSnapshot,
    OkResult,
    SecretName,
    SecretSet,
    SecretStatus,
    Settings,
    SettingsPatch,
)
from .service import ConnectionProbe, SettingsService


def register(
    dispatcher: Dispatcher,
    settings: SettingsService,
    secrets: SecretsService,
    db: Database,
    platform_name: str,
    engine: EngineSnapshot | Callable[[], EngineSnapshot],
    probe: ConnectionProbe,
    *,
    before_change: Callable[[], None] | None = None,
    change_guard: Callable[[], AbstractContextManager[None]] | None = None,
) -> None:
    def snapshot() -> EngineSnapshot:
        return engine() if callable(engine) else engine

    @contextmanager
    def change() -> Iterator[None]:
        # 组合根可注入整段配置写入护栏，消除检查与写入之间的扫描启动竞态。
        if change_guard is not None:
            with change_guard():
                yield
            return
        if before_change is not None:
            before_change()
        yield

    def bootstrap(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return settings.bootstrap(
            snapshot(), secrets, db, platform_name, os.environ.get("SENTINEL_OFFLINE") == "1"
        )

    def get(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return settings.get()

    def update(params: BaseModel, ctx: RequestContext) -> BaseModel:
        with change():
            return settings.update(cast(SettingsPatch, params))

    def test_connection(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return settings.test_connection(probe, snapshot())

    def set_key(params: BaseModel, ctx: RequestContext) -> BaseModel:
        with change():
            secrets.set_jev_key(cast(SecretSet, params).value)
        return OkResult(ok=True)

    def clear(params: BaseModel, ctx: RequestContext) -> BaseModel:
        with change():
            secrets.clear_jev_key()
        return OkResult(ok=True)

    def status(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return SecretStatus.model_validate(secrets.status())

    specs = (
        ("app.bootstrap", bootstrap, EmptyParams, Bootstrap, 30_000),
        ("settings.get", get, EmptyParams, Settings, 30_000),
        ("settings.update", update, SettingsPatch, Settings, 30_000),
        ("settings.testConnection", test_connection, EmptyParams, ConnectionTestResult, 20_000),
        ("secrets.set", set_key, SecretSet, OkResult, 30_000),
        ("secrets.clear", clear, SecretName, OkResult, 30_000),
        ("secrets.status", status, EmptyParams, SecretStatus, 30_000),
    )
    if any(dispatcher.lookup(name) is not None for name, *_ in specs):
        raise ValueError("duplicate settings method")
    settings.bind_secrets(secrets)
    for name, handler, params_model, result_model, timeout in specs:
        dispatcher.register(name, handler, params_model, result_model, timeout)
