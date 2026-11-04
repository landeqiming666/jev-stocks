from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from sentinel.clock import parse_iso
from sentinel.domain.contact import is_valid_sec_email
from sentinel.errors import UserError

MODEL_ID: Literal["jev-1.14.0"] = "jev-1.14.0"
EngineChoice = Literal["auto", "jevdb", "jev_direct"]
Engine = Literal["jevdb", "jev_direct"]
Budget = Annotated[int, Field(ge=10_000, le=50_000_000)]
Lookback = Annotated[int, Field(ge=1, le=30)]


def _email(value: str) -> str:
    if not is_valid_sec_email(value):
        raise ValueError("invalid email")
    return value


Email = Annotated[str, Field(max_length=120), AfterValidator(_email)]


class WireModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        revalidate_instances="always",
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
    )


class SettingsPatch(WireModel):
    engine: EngineChoice = "auto"
    sec_contact_email: Email | None = None
    daily_token_budget: Budget = 2_000_000
    first_scan_lookback_days: Lookback = 7

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, values: object) -> object:
        if isinstance(values, Mapping):
            values = dict(values)
            for name in ("sec_contact_email", "secContactEmail"):
                value = values.get(name)
                if isinstance(value, str):
                    values[name] = value.strip() or None
        return values

    @model_validator(mode="wrap")
    @classmethod
    def user_error(
        cls, values: object, handler: ModelWrapValidatorHandler[SettingsPatch]
    ) -> SettingsPatch:
        try:
            return handler(values)
        except ValidationError as exc:
            loc = exc.errors()[0]["loc"]
            field = ".".join(
                cls.model_fields[part].alias or part if part in cls.model_fields else str(part)
                for part in loc
            )
            key = "settings.email_invalid" if field == "secContactEmail" else None
            raise UserError("INVALID_ARGUMENT", message_key=key, field=field) from None


class StoredSettings(WireModel):
    engine: EngineChoice = "auto"
    model_id: Literal["jev-1.14.0"] = MODEL_ID
    sec_contact_email: Email | None = None
    daily_token_budget: Budget = 2_000_000
    first_scan_lookback_days: Lookback = 7
    demo_data_loaded: bool = False
    last_ticker_refresh_at: str | None = None
    last_price_refresh_at: str | None = None

    @field_validator("last_ticker_refresh_at", "last_price_refresh_at")
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
    model_id: Literal["jev-1.14.0"]
    sec_contact_email: Email | None
    daily_token_budget: Budget
    first_scan_lookback_days: Lookback
    demo_data_loaded: bool
    language: Literal["zh-CN"]
    allowed_domains: list[DomainRule] = Field(min_length=5, max_length=5)


@dataclass(frozen=True)
class EngineSnapshot:
    requested: EngineChoice
    active: Engine | None
    jevdb_available: bool


class BootstrapEngine(WireModel):
    requested: EngineChoice
    active: Engine | None
    model_id: Literal["jev-1.14.0"]
    jevdb_available: bool


class Configured(WireModel):
    jev_key: bool
    sec_email: bool


class Bootstrap(WireModel):
    protocol_version: Literal["1.0"]
    app_version: str
    db_schema_version: int = Field(ge=0)
    platform: Literal["macos", "windows"]
    engine: BootstrapEngine
    markets: list[Literal["us"]] = Field(min_length=1, max_length=1)
    configured: Configured
    demo_data_loaded: bool
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
    latency_ms: int | None = Field(default=None, ge=0)
    message: str = ""


class ConnectionCheck(ProbeResult):
    name: Literal["Jev", "SEC", "JEVDB"]


class ConnectionTestResult(WireModel):
    ok: bool
    engine: Engine | None
    model_id: Literal["jev-1.14.0"]
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

    @model_validator(mode="wrap")
    @classmethod
    def user_error(cls, values: object, handler: ModelWrapValidatorHandler[SecretSet]) -> SecretSet:
        try:
            return handler(values)
        except ValidationError as exc:
            field = ".".join(str(part) for part in exc.errors()[0]["loc"])
            key = "settings.secret_invalid" if field == "value" else None
            raise UserError("INVALID_ARGUMENT", message_key=key, field=field) from None


class SecretStatus(WireModel):
    jev_key: bool


class OkResult(WireModel):
    ok: Literal[True]

    @field_validator("ok", mode="before")
    @classmethod
    def true_bool(cls, value: object) -> object:
        if value is not True:
            raise ValueError("true boolean required")
        return value
