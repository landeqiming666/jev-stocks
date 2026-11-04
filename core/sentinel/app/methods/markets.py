"""markets 适配器：instruments.search 与 prices.refresh。"""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel

from sentinel.markets.instruments import SearchResult
from sentinel.rpc import Dispatcher
from sentinel.rpc.dispatcher import RequestContext

from ..container import AppContainer
from ..wire import RefreshParamsWire, RefreshResultWire, SearchParamsWire, SearchResultWire


def register(dispatcher: Dispatcher, container: AppContainer) -> None:
    def search(params: BaseModel, ctx: RequestContext) -> BaseModel:
        p = cast(SearchParamsWire, params)
        hits = container.instruments.search(p.query, p.limit)
        wire = SearchResult.from_hits(hits).to_wire()
        return SearchResultWire.model_validate(wire, strict=False)

    def refresh(params: BaseModel, ctx: RequestContext) -> BaseModel:
        p = cast(RefreshParamsWire, params)
        result = container.prices.refresh(p.instrument_ids)
        return RefreshResultWire.model_validate(result.to_wire(), strict=False)

    dispatcher.register("instruments.search", search, SearchParamsWire, SearchResultWire, 20_000)
    dispatcher.register("prices.refresh", refresh, RefreshParamsWire, RefreshResultWire, 120_000)


__all__ = ["register"]
