from __future__ import annotations

import os
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
    engine: EngineSnapshot,
    probe: ConnectionProbe,
) -> None:
    def bootstrap(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return settings.bootstrap(
            engine, secrets, db, platform_name, os.environ.get("SENTINEL_OFFLINE") == "1"
        )

    def get(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return settings.get()

    def update(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return settings.update(cast(SettingsPatch, params))

    def test_connection(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return settings.test_connection(probe, engine)

    def set_key(params: BaseModel, ctx: RequestContext) -> BaseModel:
        secrets.set_jev_key(cast(SecretSet, params).value)
        return OkResult(ok=True)

    def clear(params: BaseModel, ctx: RequestContext) -> BaseModel:
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
