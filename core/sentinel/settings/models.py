from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    ValidationError,
    field_validator,
    model_validator,
)

from sentinel.clock import parse_iso
from sentinel.errors import UserError

MODEL_ID: Literal["jev-1.14.0"] = "jev-1.14.0"
EngineChoice = Literal["auto", "jevdb", "jev_direct"]
Engine = Literal["jevdb", "jev_direct"]
Budget = Annotated[int, Field(ge=10_000, le=50_000_000)]
Lookback = Annotated[int, Field(ge=1, le=30)]
Email = Annotated[str, Field(max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]


class WireModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", revalidate_instances="always")


class SettingsPatch(WireModel):
    engine: EngineChoice = "auto"
    secContactEmail: Email | None = None
    dailyTokenBudget: Budget = 2_000_000
    firstScanLookbackDays: Lookback = 7

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, values: object) -> object:
        if isinstance(values, Mapping):
            values = dict(values)
            for name in ("engine", "secContactEmail"):
                value = values.get(name)
                if isinstance(value, str):
                    values[name] = value.strip()
            if values.get("secContactEmail") == "":
                values["secContactEmail"] = None
        return values

    @model_validator(mode="wrap")
    @classmethod
    def user_error(
        cls, values: object, handler: ModelWrapValidatorHandler[SettingsPatch]
    ) -> SettingsPatch:
        try:
            return handler(values)
        except ValidationError as exc:
            field = ".".join(str(part) for part in exc.errors()[0]["loc"])
            raise UserError("INVALID_ARGUMENT", field=field) from None


class StoredSettings(WireModel):
    engine: EngineChoice = "auto"
    modelId: Literal["jev-1.14.0"] = MODEL_ID
    secContactEmail: Email | None = None
    dailyTokenBudget: Budget = 2_000_000
    firstScanLookbackDays: Lookback = 7
    demoDataLoaded: bool = False
    lastTickerRefreshAt: str | None = None
    lastPriceRefreshAt: str | None = None

    @field_validator("lastTickerRefreshAt", "lastPriceRefreshAt")
    @classmethod
    def iso_time(cls, value: str | None) -> str | None:
        if value is not None:
            parse_iso(value)
            if not value.endswith("Z"):
                raise ValueError("UTC Z time required")
        return value


class DomainRule(WireModel):
    domain: str
    purpose: str
    sends: str


class Settings(WireModel):
    engine: EngineChoice
    modelId: Literal["jev-1.14.0"]
    secContactEmail: Email | None
    dailyTokenBudget: Budget
    firstScanLookbackDays: Lookback
    demoDataLoaded: bool
    language: Literal["zh-CN"]
    allowedDomains: list[DomainRule] = Field(min_length=5, max_length=5)


@dataclass(frozen=True)
class EngineSnapshot:
    requested: EngineChoice
    active: Engine | None
    jevdb_available: bool


class BootstrapEngine(WireModel):
    requested: EngineChoice
    active: Engine | None
    modelId: Literal["jev-1.14.0"]
    jevdbAvailable: bool


class Configured(WireModel):
    jevKey: bool
    secEmail: bool


class Bootstrap(WireModel):
    protocolVersion: Literal["1.0"]
    appVersion: str
    dbSchemaVersion: int = Field(ge=0)
    platform: Literal["macos", "windows"]
    engine: BootstrapEngine
    markets: list[Literal["us"]] = Field(min_length=1, max_length=1)
    configured: Configured
    demoDataLoaded: bool
    offline: bool
    now: str

    @field_validator("now")
    @classmethod
    def iso_time(cls, value: str) -> str:
        parse_iso(value)
        if not value.endswith("Z"):
            raise ValueError("UTC Z time required")
        return value


class ProbeResult(WireModel):
    ok: bool
    latencyMs: int | None = Field(default=None, ge=0)
    message: str = ""


class ConnectionCheck(ProbeResult):
    name: Literal["Jev", "SEC", "JEVDB"]


class ConnectionTestResult(WireModel):
    ok: bool
    engine: Engine | None
    modelId: Literal["jev-1.14.0"]
    checks: list[ConnectionCheck] = Field(min_length=3, max_length=3)

    @field_validator("checks")
    @classmethod
    def check_order(cls, values: list[ConnectionCheck]) -> list[ConnectionCheck]:
        if [value.name for value in values] != ["Jev", "SEC", "JEVDB"]:
            raise ValueError("invalid check order")
        return values


class EmptyParams(WireModel):
    pass


class SecretName(WireModel):
    name: Literal["jevKey"]


class SecretSet(SecretName):
    value: str


class SecretStatus(WireModel):
    jevKey: bool


class OkResult(WireModel):
    ok: Literal[True]

    @field_validator("ok", mode="before")
    @classmethod
    def true_bool(cls, value: object) -> object:
        if value is not True:
            raise ValueError("true boolean required")
        return value
