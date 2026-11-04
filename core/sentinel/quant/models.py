from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from sentinel.errors import UserError
from sentinel.messages.risk import text

WindowLabel = Literal["6M", "1Y", "3Y"]
PriceBasis = Literal["adj_close", "close"]
FloatArray = NDArray[np.float64]
Nonnegative = Annotated[float, Field(ge=0)]
Ratio = Annotated[float, Field(ge=0, le=1)]
SignedRatio = Annotated[float, Field(ge=-1, le=1)]


class WireModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        allow_inf_nan=False,
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
    )


class RiskParams(WireModel):
    scope: Literal["holdings"]
    window: WindowLabel
    currency: Literal["USD"]


class ExcludedAsset(WireModel):
    instrument_id: str
    symbol: str
    reason: str


class TopWeight(WireModel):
    instrument_id: str
    symbol: str
    weight: Ratio


class RiskWindow(WireModel):
    label: WindowLabel
    from_date: date = Field(alias="from")
    to: date
    observations: Annotated[int, Field(ge=2)]


class Correlation(WireModel):
    instrument_ids: list[str]
    symbols: list[str]
    matrix: list[list[SignedRatio | None]]


class Loading(WireModel):
    symbol: str
    value: SignedRatio


class SVDResult(WireModel):
    explained: Annotated[list[Ratio], Field(max_length=5)]
    loadings: Annotated[list[Loading], Field(max_length=5)]


class RiskResult(WireModel):
    as_of: date
    window: RiskWindow
    currency: Literal["USD"] = "USD"
    annualized_vol: Nonnegative
    max_drawdown: Ratio
    effective_holdings: Annotated[float, Field(ge=1)]
    top_weights: Annotated[list[TopWeight], Field(max_length=3)]
    correlation: Correlation
    svd: SVDResult
    condition_number_raw: Annotated[float, Field(ge=1)] | None
    condition_number_shrunk: Annotated[float, Field(ge=1)] | None
    warnings: list[str]
    excluded: list[ExcludedAsset]


@dataclass(frozen=True)
class PricePoint:
    trade_date: date
    close: float | None
    adj_close: float | None
    source: str | None = None


@dataclass(frozen=True)
class HoldingPoint:
    instrument_id: str
    symbol: str
    quantity: Decimal | int


@dataclass(frozen=True)
class RiskInput:
    symbols: list[str]
    instrument_ids: list[str]
    returns: FloatArray
    weights: FloatArray
    endpoint_closes: FloatArray
    window_observations: int
    periods_per_year: float
    price_basis: PriceBasis
    as_of: date
    from_date: date
    window_label: WindowLabel
    min_observations: int = 60
    return_dates: list[date] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    excluded: list[ExcludedAsset] = field(default_factory=list)


class RiskDataInsufficient(UserError):
    def __init__(
        self,
        observations: int,
        required: int = 60,
        *,
        no_holdings: bool = False,
        symbol: str | None = None,
    ) -> None:
        params: dict[str, object] = {"observations": observations, "required": required}
        if symbol is not None:
            params["symbol"] = symbol
        super().__init__(
            "DATA_INSUFFICIENT",
            params=params,
            reason="NO_HOLDINGS" if no_holdings else "INSUFFICIENT_OBSERVATIONS",
        )
        self._local_key = "risk.no_holdings" if no_holdings else "risk.insufficient"

    def to_wire(self, request_id: str | None = None) -> dict[str, object]:
        # 公共 initializer 由主 agent 注册；本包真实 RPC 仍需完整中文错误。
        wire = super().to_wire(request_id)
        message = text(self._local_key, self.params)
        if "symbol" in self.params:
            message += text("risk.limiting_symbol", self.params)
        wire["message"] = message
        return wire
